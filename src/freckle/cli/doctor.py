"""Doctor command for health check diagnostics."""

import json
import subprocess
import urllib.request
from dataclasses import dataclass, field
from typing import List, Optional, Set

import typer
import yaml

from ..config import Config
from ..tools_registry import get_tools_from_config
from ..utils import get_version
from .helpers import (
    CONFIG_PATH,
    get_config,
    get_dotfiles_dir,
    get_dotfiles_manager,
    is_git_available,
)
from .output import (
    console,
    error,
    info,
    muted,
    plain,
    success,
    warning,
)

# ─────────────────────────────────────────────────────────────────────────────
# Data structures for branch analysis
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class RemoteStatus:
    """Remote tracking status for a branch."""

    exists: bool
    commit: Optional[str] = None
    ahead: int = 0
    behind: int = 0
    diverged: bool = False


@dataclass
class ConfigDiff:
    """Semantic diff between two configs."""

    missing_profiles: Set[str] = field(default_factory=set)
    extra_profiles: Set[str] = field(default_factory=set)
    missing_tools: Set[str] = field(default_factory=set)
    extra_tools: Set[str] = field(default_factory=set)

    def has_differences(self) -> bool:
        return bool(
            self.missing_profiles
            or self.extra_profiles
            or self.missing_tools
            or self.extra_tools
        )


@dataclass
class BranchAnalysis:
    """Analysis of a single branch's state."""

    name: str
    local_head: str
    local_commit_msg: str
    local_commit_time: str
    remote: RemoteStatus
    config_matches: bool
    config_diff: Optional[ConfigDiff] = None
    in_config: bool = True


@dataclass
class RemoteBranch:
    """A remote branch without a local tracking branch."""

    name: str
    last_commit_time: str


# ─────────────────────────────────────────────────────────────────────────────
# Branch analysis functions
# ─────────────────────────────────────────────────────────────────────────────


def _diff_configs(current: str, other: str) -> ConfigDiff:
    """Compute semantic diff between two config strings."""
    try:
        current_data = yaml.safe_load(current) or {}
        other_data = yaml.safe_load(other) or {}
    except yaml.YAMLError:
        return ConfigDiff()

    # Compare profiles
    current_profiles = set((current_data.get("profiles") or {}).keys())
    other_profiles = set((other_data.get("profiles") or {}).keys())

    # Compare tools
    current_tools = set((current_data.get("tools") or {}).keys())
    other_tools = set((other_data.get("tools") or {}).keys())

    return ConfigDiff(
        missing_profiles=current_profiles - other_profiles,
        extra_profiles=other_profiles - current_profiles,
        missing_tools=current_tools - other_tools,
        extra_tools=other_tools - current_tools,
    )


def _analyze_branch(
    dotfiles, branch: str, current_config: Optional[str], profiles: set
) -> BranchAnalysis:
    """Analyze a single branch's state."""
    # Get local HEAD info
    try:
        local_head = dotfiles._git.run(
            "rev-parse", "--short", branch
        ).stdout.strip()
    except subprocess.CalledProcessError:
        local_head = "unknown"

    try:
        local_commit_msg = dotfiles._git.run(
            "log", "-1", "--format=%s", branch
        ).stdout.strip()
        # Truncate long messages
        if len(local_commit_msg) > 50:
            local_commit_msg = local_commit_msg[:47] + "..."
    except subprocess.CalledProcessError:
        local_commit_msg = ""

    try:
        local_commit_time = dotfiles._git.run(
            "log", "-1", "--format=%ar", branch
        ).stdout.strip()
    except subprocess.CalledProcessError:
        local_commit_time = ""

    # Check remote tracking
    remote = _get_remote_status(dotfiles, branch)

    # Check config on this branch
    branch_config = _get_config_from_branch(dotfiles, branch)
    if current_config is None or branch_config is None:
        config_matches = True
        config_diff = None
    elif branch_config == current_config:
        config_matches = True
        config_diff = None
    else:
        config_matches = False
        config_diff = _diff_configs(current_config, branch_config)

    return BranchAnalysis(
        name=branch,
        local_head=local_head,
        local_commit_msg=local_commit_msg,
        local_commit_time=local_commit_time,
        remote=remote,
        config_matches=config_matches,
        config_diff=config_diff,
        in_config=branch in profiles,
    )


def _get_remote_status(dotfiles, branch: str) -> RemoteStatus:
    """Get remote tracking status for a branch."""
    try:
        remote_head = dotfiles._git.run(
            "rev-parse", "--short", f"origin/{branch}"
        ).stdout.strip()
    except subprocess.CalledProcessError:
        return RemoteStatus(exists=False)

    # Calculate ahead/behind
    try:
        result = dotfiles._git.run(
            "rev-list", "--left-right", "--count",
            f"{branch}...origin/{branch}"
        )
        ahead, behind = map(int, result.stdout.strip().split())

        # Check for divergence (both ahead AND behind)
        diverged = ahead > 0 and behind > 0

        return RemoteStatus(
            exists=True,
            commit=remote_head,
            ahead=ahead,
            behind=behind,
            diverged=diverged,
        )
    except subprocess.CalledProcessError:
        return RemoteStatus(exists=True, commit=remote_head)


def _get_remote_only_branches(dotfiles) -> List[RemoteBranch]:
    """Find remote branches with no local tracking branch."""
    # Get all remote branches
    try:
        result = dotfiles._git.run(
            "branch", "-r", "--format=%(refname:short)"
        )
        remote_branches = [
            b.replace("origin/", "")
            for b in result.stdout.strip().split("\n")
            if b.startswith("origin/") and "HEAD" not in b
        ]
    except subprocess.CalledProcessError:
        return []

    # Get local branches
    local_branches = _get_local_branches(dotfiles)

    # Find remote-only
    remote_only = []
    for branch in remote_branches:
        if branch not in local_branches:
            try:
                last_commit = dotfiles._git.run(
                    "log", "-1", "--format=%ar", f"origin/{branch}"
                ).stdout.strip()
            except subprocess.CalledProcessError:
                last_commit = "unknown"

            remote_only.append(RemoteBranch(
                name=branch,
                last_commit_time=last_commit,
            ))

    return remote_only


def _print_branch_analysis(
    branches: List[BranchAnalysis],
    current_branch: Optional[str],
    verbose: bool,
) -> tuple[list[str], list[str]]:
    """Print branch analysis and return issues/warnings."""
    issues = []
    warnings = []

    for branch in branches:
        is_current = branch.name == current_branch

        # Build status indicators
        status_parts = []

        # Remote sync status
        if not branch.remote.exists:
            status_parts.append("no remote")
        elif branch.remote.diverged:
            status_parts.append(
                f"diverged ({branch.remote.ahead}↑ {branch.remote.behind}↓)"
            )
        elif branch.remote.ahead > 0 and branch.remote.behind > 0:
            status_parts.append(
                f"{branch.remote.ahead}↑ {branch.remote.behind}↓"
            )
        elif branch.remote.ahead > 0:
            status_parts.append(f"{branch.remote.ahead} unpushed")
        elif branch.remote.behind > 0:
            status_parts.append(f"{branch.remote.behind} behind")
        else:
            status_parts.append("synced")

        # Config status
        if not branch.config_matches:
            status_parts.append("config differs")

        # Not in config
        if not branch.in_config:
            status_parts.append("not in config")

        status_str = ", ".join(status_parts)

        # Determine icon
        if branch.remote.diverged or not branch.config_matches:
            icon = "✗"
            color = "red"
        elif (branch.remote.ahead > 0 or branch.remote.behind > 0
              or not branch.remote.exists or not branch.in_config):
            icon = "⚠"
            color = "yellow"
        else:
            icon = "✓"
            color = "green"

        # Print branch line
        if is_current:
            console.print(
                f"  [{color}]{icon}[/{color}] [bold]{branch.name}[/bold] "
                f"— {status_str}"
            )
        else:
            console.print(
                f"  [{color}]{icon}[/{color}] {branch.name} — {status_str}"
            )

        # Verbose: show commit info
        if verbose:
            muted(f"      {branch.local_head}: {branch.local_commit_msg}")
            if branch.local_commit_time:
                muted(f"      ({branch.local_commit_time})")

        # Show config diff details
        if not branch.config_matches and branch.config_diff:
            diff = branch.config_diff
            if diff.missing_profiles:
                names = ", ".join(diff.missing_profiles)
                muted(f"      missing profiles: {names}")
            if diff.extra_profiles:
                names = ", ".join(diff.extra_profiles)
                muted(f"      extra profiles: {names}")
            if diff.missing_tools:
                names = ", ".join(diff.missing_tools)
                muted(f"      missing tools: {names}")
            if diff.extra_tools:
                names = ", ".join(diff.extra_tools)
                muted(f"      extra tools: {names}")

        # Collect warnings/issues
        if branch.remote.diverged:
            issues.append(f"Branch '{branch.name}' has diverged from remote")
        if not branch.config_matches:
            warnings.append(f"Config differs on '{branch.name}'")
        if not branch.in_config:
            warnings.append(f"Branch '{branch.name}' not in config")
        if branch.remote.ahead > 0:
            warnings.append(
                f"{branch.remote.ahead} unpushed commit(s) on '{branch.name}'"
            )

    return issues, warnings


def _print_remote_only_branches(
    remote_branches: List[RemoteBranch], verbose: bool
) -> list[str]:
    """Print remote-only branches and return warnings."""
    warnings = []

    if not remote_branches:
        return warnings

    plain("")
    plain("  Remote-only branches:")

    for rb in remote_branches:
        msg = f"{rb.name} (last commit: {rb.last_commit_time})"
        warning(msg, prefix="    ⚠")
        warnings.append(f"Remote branch '{rb.name}' not tracked locally")

        if verbose:
            muted(f"      To track: git checkout {rb.name}")
            muted(f"      To delete: git push origin --delete {rb.name}")

    return warnings


def register(app: typer.Typer) -> None:
    """Register the doctor command with the app."""
    app.command()(doctor)


def doctor(
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Show detailed output"
    ),
):
    """Run health checks and show system status.

    Checks:
    - Dotfiles repository status
    - Config file validity
    - Tool installation status
    - Profile configuration

    Example:
        freckle doctor
        freckle doctor --verbose
    """
    issues = []
    warnings = []

    plain("Running freckle health check...\n")

    # Check freckle version
    plain("Freckle:")
    version_warnings = _check_version(verbose)
    warnings.extend(version_warnings)

    plain("")

    # Check prerequisites
    plain("Prerequisites:")
    prereq_issues = _check_prerequisites(verbose)
    issues.extend(prereq_issues)

    plain("")

    # Check config
    plain("Config:")
    config_issues, config_warnings = _check_config(verbose)
    issues.extend(config_issues)
    warnings.extend(config_warnings)

    plain("")

    # Check dotfiles
    plain("Dotfiles:")
    df_issues, df_warnings = _check_dotfiles(verbose)
    issues.extend(df_issues)
    warnings.extend(df_warnings)

    plain("")

    # Check branches (detailed analysis)
    plain("Branches:")
    branch_issues, branch_warnings = _check_branches(verbose)
    issues.extend(branch_issues)
    warnings.extend(branch_warnings)

    plain("")

    # Check tools
    plain("Tools:")
    tool_issues, tool_warnings = _check_tools(verbose)
    issues.extend(tool_issues)
    warnings.extend(tool_warnings)

    plain("")

    # Summary
    if issues or warnings:
        plain("─" * 40)
        if warnings:
            console.print(f"[yellow]Warnings: {len(warnings)}[/yellow]")
            for w in warnings:
                warning(w, prefix="  ⚠")
        if issues:
            console.print(f"[red]Issues: {len(issues)}[/red]")
            for i in issues:
                error(i, prefix="  ✗")

        plain("")
        plain("Suggestions:")
        _print_suggestions(issues, warnings)
        raise typer.Exit(1 if issues else 0)
    else:
        success("All checks passed!")


def _get_latest_version() -> Optional[str]:
    """Fetch the latest version from PyPI."""
    try:
        url = "https://pypi.org/pypi/freckle/json"
        with urllib.request.urlopen(url, timeout=5) as response:
            data = json.loads(response.read().decode())
            return data.get("info", {}).get("version")
    except Exception:
        return None


def _check_version(verbose: bool) -> list[str]:
    """Check if freckle is up to date."""
    warnings = []

    current = get_version()
    plain(f"  Current version: {current}")

    latest = _get_latest_version()
    if latest:
        if latest != current:
            warning(f"New version available: {latest}", prefix="  ⚠")
            msg = f"Freckle {latest} available (you have {current})"
            warnings.append(msg)
        else:
            success("Up to date", prefix="  ✓")
    else:
        if verbose:
            warning("Could not check for updates", prefix="  ⚠")

    return warnings


def _check_prerequisites(verbose: bool) -> list[str]:
    """Check required system prerequisites."""
    issues = []

    if is_git_available():
        success("git is installed", prefix="  ✓")
    else:
        error("git is not installed", prefix="  ✗")
        issues.append("git is not installed")

    return issues


def _check_config(verbose: bool) -> tuple[list[str], list[str]]:
    """Check config file validity."""
    issues = []
    warnings = []

    if not CONFIG_PATH.exists():
        error("No config file found", prefix="  ✗")
        issues.append(f"Missing {CONFIG_PATH}")
        return issues, warnings

    success(f"Config file: {CONFIG_PATH}", prefix="  ✓")

    try:
        config = Config(CONFIG_PATH)
        success("Valid YAML syntax", prefix="  ✓")
    except Exception as e:
        error(f"Invalid YAML: {e}", prefix="  ✗")
        issues.append(f"Config parse error: {e}")
        return issues, warnings

    # Check for unknown keys
    known_keys = {"vars", "dotfiles", "profiles", "tools", "secrets"}
    unknown_keys = set(config.data.keys()) - known_keys
    if unknown_keys:
        for key in unknown_keys:
            warning(f"Unknown key: '{key}'", prefix="  ⚠")
            warnings.append(f"Unknown config key: '{key}'")

    # Check profiles
    profiles = config.get_profiles()
    if profiles:
        success(f"Profiles configured: {len(profiles)}", prefix="  ✓")
        if verbose:
            for name in profiles:
                muted(f"      - {name}")

    return issues, warnings


def _check_dotfiles(verbose: bool) -> tuple[list[str], list[str]]:
    """Check dotfiles repository status."""
    issues = []
    warnings = []

    try:
        config = get_config()
    except Exception:
        error("Could not load config", prefix="  ✗")
        issues.append("Config load failed")
        return issues, warnings

    dotfiles_dir = get_dotfiles_dir(config)

    if not dotfiles_dir.exists():
        error("Repository not initialized", prefix="  ✗")
        issues.append("Dotfiles repo not found")
        return issues, warnings

    success(f"Repository: {dotfiles_dir}", prefix="  ✓")

    dotfiles = get_dotfiles_manager(config)
    if not dotfiles:
        error("Could not create dotfiles manager", prefix="  ✗")
        issues.append("Dotfiles manager init failed")
        return issues, warnings

    # Check current branch
    try:
        result = dotfiles._git.run("rev-parse", "--abbrev-ref", "HEAD")
        branch = result.stdout.strip()
        success(f"Branch: {branch}", prefix="  ✓")
    except subprocess.CalledProcessError:
        warning("Could not determine branch", prefix="  ⚠")
        warnings.append("Could not determine current branch")
        branch = None

    # Check remote status
    try:
        dotfiles._git.run("fetch", "--dry-run")
        success("Remote accessible", prefix="  ✓")
    except subprocess.CalledProcessError:
        warning("Could not reach remote", prefix="  ⚠")
        warnings.append("Remote not accessible")

    # Check for local changes (only tracked files, ignore untracked)
    try:
        result = dotfiles._git.run("status", "--porcelain")
        output = result.stdout.strip()
        all_changes = output.split("\n") if output else []
        # Filter out untracked files (lines starting with ??)
        tracked_changes = [
            line for line in all_changes
            if line and not line.startswith("??")
        ]
        if tracked_changes:
            num_changes = len(tracked_changes)
            warning(f"{num_changes} modified file(s)", prefix="  ⚠")
            warnings.append(f"{num_changes} uncommitted changes")
            if verbose:
                for line in tracked_changes[:5]:
                    muted(f"      {line}")
                if num_changes > 5:
                    muted(f"      ... and {num_changes - 5} more")
        else:
            success("Working tree clean", prefix="  ✓")
    except subprocess.CalledProcessError:
        pass

    return issues, warnings


def _check_branches(verbose: bool) -> tuple[list[str], list[str]]:
    """Comprehensive branch analysis: local, remote, config alignment."""
    issues = []
    warnings = []

    try:
        config = get_config()
    except Exception:
        return issues, warnings

    dotfiles = get_dotfiles_manager(config)
    if not dotfiles:
        muted("  (skipped - no dotfiles manager)")
        return issues, warnings

    # Get current branch
    try:
        result = dotfiles._git.run("rev-parse", "--abbrev-ref", "HEAD")
        current_branch = result.stdout.strip()
    except subprocess.CalledProcessError:
        current_branch = None

    # Get current config content for comparison
    current_config = None
    if current_branch:
        current_config = _get_config_from_branch(dotfiles, current_branch)

    # Get all local branches
    local_branches = _get_local_branches(dotfiles)
    if not local_branches:
        muted("  No local branches found")
        return issues, warnings

    # Get profiles from config
    profiles = set(config.get_profiles().keys())

    # Analyze each local branch
    branch_analyses = []
    for branch in local_branches:
        analysis = _analyze_branch(dotfiles, branch, current_config, profiles)
        branch_analyses.append(analysis)

    # Print branch analysis
    branch_issues, branch_warnings = _print_branch_analysis(
        branch_analyses, current_branch, verbose
    )
    issues.extend(branch_issues)
    warnings.extend(branch_warnings)

    # Check for remote-only branches
    remote_only = _get_remote_only_branches(dotfiles)
    remote_warnings = _print_remote_only_branches(remote_only, verbose)
    warnings.extend(remote_warnings)

    return issues, warnings


def _get_config_from_branch(dotfiles, branch: str) -> Optional[str]:
    """Get freckle config content from a branch, checking both extensions."""
    for ext in (".freckle.yaml", ".freckle.yml"):
        try:
            return dotfiles._git.run("show", f"{branch}:{ext}").stdout
        except subprocess.CalledProcessError:
            continue
    return None


def _get_local_branches(dotfiles) -> list[str]:
    """Get all local branches in the dotfiles repo."""
    try:
        result = dotfiles._git.run("branch", "--list")
        branches = [
            b.strip().lstrip("* ")
            for b in result.stdout.split("\n")
            if b.strip()
        ]
        return branches
    except subprocess.CalledProcessError:
        return []


def _check_tools(verbose: bool) -> tuple[list[str], list[str]]:
    """Check tool installation status."""
    issues = []
    warnings = []

    try:
        config = get_config()
    except Exception:
        error("Could not load config", prefix="  ✗")
        issues.append("Config load failed")
        return issues, warnings

    registry = get_tools_from_config(config)
    all_tools = registry.list_tools()

    if not all_tools:
        plain("  No tools configured")
        return issues, warnings

    # Filter by active profile's modules
    dotfiles = get_dotfiles_manager(config)
    if dotfiles:
        from .profile.helpers import get_current_branch
        current_branch = get_current_branch(config=config, dotfiles=dotfiles)
        if current_branch:
            active_modules = config.get_profile_modules(current_branch)
            if active_modules:
                tools = [t for t in all_tools if t.name in active_modules]
            else:
                tools = all_tools
        else:
            tools = all_tools
    else:
        tools = all_tools

    if not tools:
        plain("  No tools for current profile")
        return issues, warnings

    installed = 0
    not_installed = []

    for tool in tools:
        if tool.is_installed():
            installed += 1
            if verbose:
                version = tool.get_version() or "installed"
                if len(version) > 30:
                    version = version[:27] + "..."
                success(f"{tool.name}: {version}", prefix="  ✓")
        else:
            not_installed.append(tool.name)
            if verbose:
                error(f"{tool.name}: not installed", prefix="  ✗")

    if not verbose:
        if installed > 0:
            success(f"{installed} tool(s) installed", prefix="  ✓")
        if not_installed:
            error(f"{len(not_installed)} tool(s) missing", prefix="  ✗")
            for name in not_installed[:3]:
                muted(f"      - {name}")
            if len(not_installed) > 3:
                muted(f"      - ... and {len(not_installed) - 3} more")

    if not_installed:
        warnings.append(
            f"{len(not_installed)} configured tools not installed"
        )

    return issues, warnings


def _print_suggestions(issues: list[str], warnings: list[str]) -> None:
    """Print suggestions based on issues and warnings."""
    suggestions = []

    for item in issues + warnings:
        if "available (you have" in item:
            suggestions.append("Run 'freckle upgrade' to update freckle")
        elif "git is not installed" in item:
            suggestions.append(
                "Install git: brew install git (macOS) "
                "or apt install git (Linux)"
            )
        elif "Missing" in item and ".freckle" in item:
            suggestions.append("Run 'freckle init' to set up configuration")
        elif "Dotfiles repo not found" in item:
            suggestions.append("Run 'freckle init' to set up your dotfiles")
        elif "uncommitted changes" in item:
            suggestions.append("Run 'freckle save' to save local changes")
        elif "unpushed commit" in item:
            suggestions.append("Run 'freckle push' to push changes to remote")
        elif "behind" in item:
            suggestions.append("Run 'freckle fetch' to get latest changes")
        elif "tools not installed" in item:
            suggestions.append("Run 'freckle tools' to see missing tools")
        elif "Config differs" in item:
            suggestions.append(
                "Run 'freckle save' to sync config to all branches"
            )
        elif "not in config" in item:
            suggestions.append(
                "Add missing branches to config with "
                "'freckle profile create <name>'"
            )
        elif "diverged" in item.lower():
            suggestions.append(
                "Resolve diverged branches manually:\n"
                "      git rebase origin/<branch>  (replay local on remote)\n"
                "      git merge origin/<branch>   (create merge commit)"
            )
        elif "not tracked locally" in item:
            suggestions.append(
                "Track remote branches or delete stale ones:\n"
                "      git checkout <branch>              (to track)\n"
                "      git push origin --delete <branch>  (to delete)"
            )

    # Dedupe and print
    for suggestion in dict.fromkeys(suggestions):
        info(f"  → {suggestion}")
