"""Profile operations: list, show, switch, diff."""

import subprocess

import typer

from ..helpers import (
    CONFIG_FILENAME,
    env,
    get_dotfiles_dir,
    get_dotfiles_manager,
    get_subprocess_error,
)
from .helpers import get_current_branch


def profile_list(config, profiles):
    """List all profiles."""
    if not profiles:
        typer.echo("No profiles configured.")
        typer.echo(f"\nTo create a profile, add to {CONFIG_FILENAME}:")
        typer.echo("  profiles:")
        typer.echo("    main:")
        typer.echo('      description: "My main config"')
        typer.echo("      modules: [zsh, nvim]")
        return

    current_branch = get_current_branch(config=config)

    typer.echo("Available profiles:\n")
    for name, profile in profiles.items():
        branch = name  # Profile name = branch name
        desc = profile.get("description", "")
        modules = profile.get("modules", [])

        is_current = current_branch == branch
        marker = "*" if is_current else " "

        typer.echo(f"  {marker} {name}")
        if desc:
            typer.echo(f"      {desc}")
        if modules:
            typer.echo(f"      modules: {', '.join(modules)}")
        if branch != name:
            typer.echo(f"      branch: {branch}")


def profile_show(config, profiles):
    """Show current profile details."""
    current_branch = get_current_branch(config=config)

    if not current_branch:
        typer.echo("No dotfiles repository found.")
        return

    # Find profile matching current branch
    current_profile = None
    for name, profile in profiles.items():
        branch = name  # Profile name = branch name
        if branch == current_branch:
            current_profile = name
            break

    if current_profile:
        profile = profiles[current_profile]
        typer.echo(f"Current profile: {current_profile}")
        typer.echo(f"  Branch: {current_branch}")
        if profile.get("description"):
            typer.echo(f"  Description: {profile['description']}")
        modules = profile.get("modules", [])
        if modules:
            typer.echo(f"  Modules: {', '.join(modules)}")
    else:
        typer.echo(f"Current branch: {current_branch}")
        typer.echo("  (not matching any defined profile)")


def profile_switch(config, name, force):
    """Switch to a different profile."""
    profiles = config.get_profiles()

    if name not in profiles:
        typer.echo(f"Profile not found: {name}", err=True)
        typer.echo("\nAvailable profiles:")
        for p in profiles:
            typer.echo(f"  - {p}")
        raise typer.Exit(1)

    profile = profiles[name]
    target_branch = name  # Profile name = branch name

    dotfiles = get_dotfiles_manager(config)
    if not dotfiles:
        typer.echo("Dotfiles not configured.", err=True)
        raise typer.Exit(1)

    dotfiles_dir = get_dotfiles_dir(config)
    if not dotfiles_dir.exists():
        typer.echo("Dotfiles repository not found.", err=True)
        raise typer.Exit(1)

    # Check for local changes (only tracked files, not untracked)
    try:
        result = dotfiles._git.run("status", "--porcelain")
        output = result.stdout.strip()
        if output:
            # Filter out untracked files (lines starting with ??)
            tracked_changes = [
                line for line in output.split("\n")
                if line and not line.startswith("??")
            ]
            has_changes = bool(tracked_changes)
        else:
            has_changes = False
    except subprocess.CalledProcessError:
        has_changes = False

    if has_changes and not force:
        typer.echo("You have uncommitted changes.")
        typer.echo("Use --force to discard them, or run 'freckle backup'.")
        raise typer.Exit(1)

    # Switch branch
    typer.echo(f"Switching to profile '{name}' (branch: {target_branch})...")

    try:
        if has_changes:
            # Backup before discarding
            from freckle.backup import BackupManager

            backup_manager = BackupManager()
            report = dotfiles.get_detailed_status()
            changed_files = report.get("changed_files", [])
            if changed_files:
                point = backup_manager.create_restore_point(
                    files=changed_files,
                    reason="pre-profile-switch",
                    home=env.home,
                )
                if point:
                    typer.echo(f"  (backed up {len(point.files)} files)")

            dotfiles._git.run("checkout", "--force", target_branch)
        else:
            dotfiles._git.run("checkout", target_branch)

        typer.echo(f"✓ Switched to profile '{name}'")

        # Show modules for this profile
        modules = profile.get("modules", [])
        if modules:
            typer.echo(f"  Modules: {', '.join(modules)}")

    except subprocess.CalledProcessError as e:
        typer.echo(f"Failed to switch: {get_subprocess_error(e)}", err=True)
        raise typer.Exit(1)


def profile_diff(config, name):
    """Show diff between current profile and another."""
    profiles = config.get_profiles()

    if name not in profiles:
        typer.echo(f"Profile not found: {name}", err=True)
        raise typer.Exit(1)

    current_branch = get_current_branch(config=config)
    target_branch = name  # Profile name = branch name

    if current_branch == target_branch:
        typer.echo(f"Already on profile '{name}'")
        return

    dotfiles = get_dotfiles_manager(config)
    if not dotfiles:
        typer.echo("Dotfiles not configured.", err=True)
        raise typer.Exit(1)

    typer.echo(f"Comparing '{current_branch}' to '{name}' ({target_branch}):")
    typer.echo("")

    try:
        # Get file differences
        result = dotfiles._git.run(
            "diff", "--stat", f"{current_branch}..{target_branch}"
        )

        if result.stdout.strip():
            typer.echo(result.stdout)
        else:
            typer.echo("No differences found.")

    except subprocess.CalledProcessError as e:
        typer.echo(f"Failed to diff: {get_subprocess_error(e)}", err=True)
        raise typer.Exit(1)
