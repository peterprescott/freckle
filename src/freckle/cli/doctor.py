"""Doctor command for health check diagnostics."""

import json
import subprocess
import urllib.request
from typing import Optional

import typer

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

    # Check if behind/ahead of remote
    if branch:
        try:
            result = dotfiles._git.run(
                "rev-list", "--left-right", "--count",
                f"{branch}...origin/{branch}"
            )
            ahead, behind = result.stdout.strip().split()
            if int(ahead) > 0:
                warning(f"{ahead} commit(s) ahead of remote", prefix="  ⚠")
                warnings.append(f"{ahead} unpushed commits")
            if int(behind) > 0:
                warning(f"{behind} commit(s) behind remote", prefix="  ⚠")
                warnings.append(f"{behind} commits behind remote")
            if int(ahead) == 0 and int(behind) == 0:
                success("Up to date with remote", prefix="  ✓")
        except subprocess.CalledProcessError:
            pass

    # Check config alignment across branches
    config_warnings = _check_config_alignment(
        config, dotfiles, branch, verbose
    )
    warnings.extend(config_warnings)

    return issues, warnings


def _get_config_from_branch(dotfiles, branch: str) -> Optional[str]:
    """Get freckle config content from a branch, checking both extensions."""
    for ext in (".freckle.yaml", ".freckle.yml"):
        try:
            return dotfiles._git.run("show", f"{branch}:{ext}").stdout
        except subprocess.CalledProcessError:
            continue
    return None


def _check_config_alignment(
    config: Config, dotfiles, current_branch: Optional[str], verbose: bool
) -> list[str]:
    """Check that freckle config is consistent across all profile branches."""
    warnings = []

    profiles = config.get_profiles()
    if not profiles or len(profiles) < 2:
        return warnings

    if current_branch is None:
        return warnings

    # Get config content from current branch
    current_config = _get_config_from_branch(dotfiles, current_branch)
    if current_config is None:
        return warnings  # Config not tracked, skip check

    mismatched = []
    for profile_name in profiles:
        if profile_name == current_branch:
            continue

        branch_config = _get_config_from_branch(dotfiles, profile_name)
        if branch_config is not None and branch_config != current_config:
            mismatched.append(profile_name)

    if mismatched:
        n = len(mismatched)
        warning(f"Config differs on {n} branch(es)", prefix="  ⚠")
        warnings.append(
            f"freckle config differs on branches: {', '.join(mismatched)}"
        )
        if verbose:
            for name in mismatched:
                muted(f"      - {name}")
    else:
        success("Config aligned across branches", prefix="  ✓")

    return warnings


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
        elif "unpushed commits" in item:
            suggestions.append("Run 'freckle save' to sync changes")
        elif "behind remote" in item:
            suggestions.append("Run 'freckle fetch' to get latest changes")
        elif "tools not installed" in item:
            suggestions.append("Run 'freckle tools' to see missing tools")
        elif "freckle config differs" in item:
            suggestions.append(
                "Run 'freckle config propagate' to sync config to all branches"
            )

    # Dedupe and print
    for suggestion in dict.fromkeys(suggestions):
        info(f"  → {suggestion}")
