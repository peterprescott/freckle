"""Doctor command for health check diagnostics."""

import subprocess
from pathlib import Path

import typer

from ..config import Config
from ..tools_registry import get_tools_from_config
from .helpers import get_config, get_dotfiles_dir, get_dotfiles_manager


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


def _check_config(verbose: bool) -> tuple[list[str], list[str]]:
    """Check config file validity."""
    issues = []
    warnings = []

    config_path = Path.home() / ".freckle.yaml"

    if not config_path.exists():
        typer.echo("  ✗ No config file found")
        issues.append("Missing ~/.freckle.yaml")
        return issues, warnings

    typer.echo(f"  ✓ Config file: {config_path}")

    try:
        config = Config(config_path)
        typer.echo("  ✓ Valid YAML syntax")
    except Exception as e:
        typer.echo(f"  ✗ Invalid YAML: {e}")
        issues.append(f"Config parse error: {e}")
        return issues, warnings

    # Check version
    version = config.data.get("version")
    if version == 2:
        typer.echo("  ✓ Config version: v2")
    elif version == 1 or version is None:
        typer.echo("  ⚠ Config version: v1 (consider updating)")
        warnings.append("Using legacy v1 config format")
    else:
        typer.echo(f"  ⚠ Unknown config version: {version}")
        warnings.append(f"Unknown config version: {version}")

    # Check for unknown keys
    known_keys = {
        "version", "dotfiles", "modules", "profiles", "tools", "secrets"
    }
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

    # Check for local changes
    try:
        result = dotfiles._git.run("status", "--porcelain")
        changes = result.stdout.strip()
        if changes:
            num_changes = len(changes.split("\n"))
            typer.echo(f"  ⚠ {num_changes} uncommitted change(s)")
            warnings.append(f"{num_changes} uncommitted changes")
            if verbose:
                for line in changes.split("\n")[:5]:
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

    return issues, warnings


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
        if "Missing ~/.freckle.yaml" in item:
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
            suggestions.append("Run 'freckle tools-list' to see missing tools")
        elif "v1 config" in item:
            suggestions.append(
                "Add 'version: 2' to config for profile support"
            )

    # Dedupe and print
    for suggestion in dict.fromkeys(suggestions):
        typer.echo(f"  → {suggestion}")
