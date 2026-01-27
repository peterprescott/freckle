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

    typer.echo("Running freckle health check...\n")

    # Check freckle version
    typer.echo("Freckle:")
    version_warnings = _check_version(verbose)
    warnings.extend(version_warnings)

    typer.echo("")

    # Check prerequisites
    typer.echo("Prerequisites:")
    prereq_issues = _check_prerequisites(verbose)
    issues.extend(prereq_issues)

    typer.echo("")

    # Check config
    typer.echo("Config:")
    config_issues, config_warnings = _check_config(verbose)
    issues.extend(config_issues)
    warnings.extend(config_warnings)

    typer.echo("")

    # Check dotfiles
    typer.echo("Dotfiles:")
    df_issues, df_warnings = _check_dotfiles(verbose)
    issues.extend(df_issues)
    warnings.extend(df_warnings)

    typer.echo("")

    # Check tools
    typer.echo("Tools:")
    tool_issues, tool_warnings = _check_tools(verbose)
    issues.extend(tool_issues)
    warnings.extend(tool_warnings)

    typer.echo("")

    # Summary
    if issues or warnings:
        typer.echo("─" * 40)
        if warnings:
            typer.echo(f"Warnings: {len(warnings)}")
            for w in warnings:
                typer.echo(f"  ⚠ {w}")
        if issues:
            typer.echo(f"Issues: {len(issues)}")
            for i in issues:
                typer.echo(f"  ✗ {i}")

        typer.echo("")
        typer.echo("Suggestions:")
        _print_suggestions(issues, warnings)
        raise typer.Exit(1 if issues else 0)
    else:
        typer.echo("✓ All checks passed!")


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
    typer.echo(f"  Current version: {current}")

    latest = _get_latest_version()
    if latest:
        if latest != current:
            typer.echo(f"  ⚠ New version available: {latest}")
            msg = f"Freckle {latest} available (you have {current})"
            warnings.append(msg)
        else:
            typer.echo("  ✓ Up to date")
    else:
        if verbose:
            typer.echo("  ⚠ Could not check for updates")

    return warnings


def _check_prerequisites(verbose: bool) -> list[str]:
    """Check required system prerequisites."""
    issues = []

    if is_git_available():
        typer.echo("  ✓ git is installed")
    else:
        typer.echo("  ✗ git is not installed")
        issues.append("git is not installed")

    return issues


def _check_config(verbose: bool) -> tuple[list[str], list[str]]:
    """Check config file validity."""
    issues = []
    warnings = []

    if not CONFIG_PATH.exists():
        typer.echo("  ✗ No config file found")
        issues.append(f"Missing {CONFIG_PATH}")
        return issues, warnings

    typer.echo(f"  ✓ Config file: {CONFIG_PATH}")

    try:
        config = Config(CONFIG_PATH)
        typer.echo("  ✓ Valid YAML syntax")
    except Exception as e:
        typer.echo(f"  ✗ Invalid YAML: {e}")
        issues.append(f"Config parse error: {e}")
        return issues, warnings

    # Check for unknown keys
    known_keys = {"vars", "dotfiles", "profiles", "tools", "secrets"}
    unknown_keys = set(config.data.keys()) - known_keys
    if unknown_keys:
        for key in unknown_keys:
            typer.echo(f"  ⚠ Unknown key: '{key}'")
            warnings.append(f"Unknown config key: '{key}'")

    # Check profiles
    profiles = config.get_profiles()
    if profiles:
        typer.echo(f"  ✓ Profiles configured: {len(profiles)}")
        if verbose:
            for name in profiles:
                typer.echo(f"      - {name}")

    return issues, warnings


def _check_dotfiles(verbose: bool) -> tuple[list[str], list[str]]:
    """Check dotfiles repository status."""
    issues = []
    warnings = []

    try:
        config = get_config()
    except Exception:
        typer.echo("  ✗ Could not load config")
        issues.append("Config load failed")
        return issues, warnings

    dotfiles_dir = get_dotfiles_dir(config)

    if not dotfiles_dir.exists():
        typer.echo("  ✗ Repository not initialized")
        issues.append("Dotfiles repo not found")
        return issues, warnings

    typer.echo(f"  ✓ Repository: {dotfiles_dir}")

    dotfiles = get_dotfiles_manager(config)
    if not dotfiles:
        typer.echo("  ✗ Could not create dotfiles manager")
        issues.append("Dotfiles manager init failed")
        return issues, warnings

    # Check current branch
    try:
        result = dotfiles._git.run("rev-parse", "--abbrev-ref", "HEAD")
        branch = result.stdout.strip()
        typer.echo(f"  ✓ Branch: {branch}")
    except subprocess.CalledProcessError:
        typer.echo("  ⚠ Could not determine branch")
        warnings.append("Could not determine current branch")
        branch = None

    # Check remote status
    try:
        dotfiles._git.run("fetch", "--dry-run")
        typer.echo("  ✓ Remote accessible")
    except subprocess.CalledProcessError:
        typer.echo("  ⚠ Could not reach remote")
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
            typer.echo(f"  ⚠ {num_changes} modified file(s)")
            warnings.append(f"{num_changes} uncommitted changes")
            if verbose:
                for line in tracked_changes[:5]:
                    typer.echo(f"      {line}")
                if num_changes > 5:
                    typer.echo(f"      ... and {num_changes - 5} more")
        else:
            typer.echo("  ✓ Working tree clean")
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
                typer.echo(f"  ⚠ {ahead} commit(s) ahead of remote")
                warnings.append(f"{ahead} unpushed commits")
            if int(behind) > 0:
                typer.echo(f"  ⚠ {behind} commit(s) behind remote")
                warnings.append(f"{behind} commits behind remote")
            if int(ahead) == 0 and int(behind) == 0:
                typer.echo("  ✓ Up to date with remote")
        except subprocess.CalledProcessError:
            pass

    # Check config alignment across branches
    config_warnings = _check_config_alignment(
        config, dotfiles, branch, verbose
    )
    warnings.extend(config_warnings)

    return issues, warnings


def _check_config_alignment(
    config: Config, dotfiles, current_branch: Optional[str], verbose: bool
) -> list[str]:
    """Check that .freckle.yaml is consistent across all profile branches."""
    warnings = []

    profiles = config.get_profiles()
    if not profiles or len(profiles) < 2:
        return warnings

    # Get config content from current branch
    try:
        current_config = dotfiles._git.run(
            "show", f"{current_branch}:.freckle.yaml"
        ).stdout
    except subprocess.CalledProcessError:
        return warnings  # Config not tracked, skip check

    mismatched = []
    for profile_name in profiles:
        if profile_name == current_branch:
            continue

        try:
            branch_config = dotfiles._git.run(
                "show", f"{profile_name}:.freckle.yaml"
            ).stdout
            if branch_config != current_config:
                mismatched.append(profile_name)
        except subprocess.CalledProcessError:
            # Branch doesn't exist or config not tracked there
            continue

    if mismatched:
        typer.echo(f"  ⚠ Config differs on {len(mismatched)} branch(es)")
        warnings.append(
            f".freckle.yaml differs on branches: {', '.join(mismatched)}"
        )
        if verbose:
            for name in mismatched:
                typer.echo(f"      - {name}")
    else:
        typer.echo("  ✓ Config aligned across branches")

    return warnings


def _check_tools(verbose: bool) -> tuple[list[str], list[str]]:
    """Check tool installation status."""
    issues = []
    warnings = []

    try:
        config = get_config()
    except Exception:
        typer.echo("  ✗ Could not load config")
        issues.append("Config load failed")
        return issues, warnings

    registry = get_tools_from_config(config)
    tools = registry.list_tools()

    if not tools:
        typer.echo("  No tools configured")
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
                typer.echo(f"  ✓ {tool.name}: {version}")
        else:
            not_installed.append(tool.name)
            if verbose:
                typer.echo(f"  ✗ {tool.name}: not installed")

    if not verbose:
        if installed > 0:
            typer.echo(f"  ✓ {installed} tool(s) installed")
        if not_installed:
            typer.echo(f"  ✗ {len(not_installed)} tool(s) missing")
            for name in not_installed[:3]:
                typer.echo(f"      - {name}")
            if len(not_installed) > 3:
                typer.echo(f"      - ... and {len(not_installed) - 3} more")

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
        elif "Missing" in item and ".freckle.yaml" in item:
            suggestions.append("Run 'freckle init' to set up configuration")
        elif "Dotfiles repo not found" in item:
            suggestions.append("Run 'freckle sync' to clone your dotfiles")
        elif "uncommitted changes" in item:
            suggestions.append("Run 'freckle backup' to save local changes")
        elif "unpushed commits" in item:
            suggestions.append("Run 'freckle git push' to push changes")
        elif "behind remote" in item:
            suggestions.append("Run 'freckle update' to pull latest changes")
        elif "tools not installed" in item:
            suggestions.append("Run 'freckle tools' to see missing tools")
        elif ".freckle.yaml differs" in item:
            suggestions.append(
                "Run 'freckle config propagate' to sync config to all branches"
            )

    # Dedupe and print
    for suggestion in dict.fromkeys(suggestions):
        typer.echo(f"  → {suggestion}")
