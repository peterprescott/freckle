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
from ..output import console, error, muted, plain, success
from .helpers import get_current_branch


def profile_list(config, profiles):
    """List all profiles."""
    if not profiles:
        plain("No profiles configured.")
        muted(f"\nTo create a profile, add to {CONFIG_FILENAME}:")
        muted("  profiles:")
        muted("    main:")
        muted('      description: "My main config"')
        muted("      modules: [zsh, nvim]")
        return

    current_branch = get_current_branch(config=config)

    plain("Available profiles:\n")
    for name, profile in profiles.items():
        branch = name  # Profile name = branch name
        desc = profile.get("description", "")
        modules = profile.get("modules", [])

        is_current = current_branch == branch

        if is_current:
            console.print(f"  [green]*[/green] [bold]{name}[/bold]")
        else:
            plain(f"    {name}")
        if desc:
            muted(f"      {desc}")
        if modules:
            muted(f"      modules: {', '.join(modules)}")
        if branch != name:
            muted(f"      branch: {branch}")


def profile_show(config, profiles):
    """Show current profile details."""
    current_branch = get_current_branch(config=config)

    if not current_branch:
        plain("No dotfiles repository found.")
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
        console.print(f"Current profile: [bold]{current_profile}[/bold]")
        muted(f"  Branch: {current_branch}")
        if profile.get("description"):
            muted(f"  Description: {profile['description']}")
        modules = profile.get("modules", [])
        if modules:
            muted(f"  Modules: {', '.join(modules)}")
    else:
        plain(f"Current branch: {current_branch}")
        muted("  (not matching any defined profile)")


def profile_switch(config, name, force):
    """Switch to a different profile."""
    profiles = config.get_profiles()

    if name not in profiles:
        error(f"Profile not found: {name}")
        plain("\nAvailable profiles:")
        for p in profiles:
            muted(f"  - {p}")
        raise typer.Exit(1)

    profile = profiles[name]
    target_branch = name  # Profile name = branch name

    dotfiles = get_dotfiles_manager(config)
    if not dotfiles:
        error("Dotfiles not configured.")
        raise typer.Exit(1)

    dotfiles_dir = get_dotfiles_dir(config)
    if not dotfiles_dir.exists():
        error("Dotfiles repository not found.")
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
        plain("You have uncommitted changes.")
        muted("Use --force to discard them, or run 'freckle save'.")
        raise typer.Exit(1)

    # Switch branch
    plain(f"Switching to profile '{name}' (branch: {target_branch})...")

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
                    muted(f"  (backed up {len(point.files)} files)")

            dotfiles._git.run("checkout", "--force", target_branch)
        else:
            dotfiles._git.run("checkout", target_branch)

        success(f"Switched to profile '{name}'")

        # Show modules for this profile
        modules = profile.get("modules", [])
        if modules:
            muted(f"  Modules: {', '.join(modules)}")

    except subprocess.CalledProcessError as e:
        error(f"Failed to switch: {get_subprocess_error(e)}")
        raise typer.Exit(1)


def profile_diff(config, name):
    """Show diff between current profile and another."""
    profiles = config.get_profiles()

    if name not in profiles:
        error(f"Profile not found: {name}")
        raise typer.Exit(1)

    current_branch = get_current_branch(config=config)
    target_branch = name  # Profile name = branch name

    if current_branch == target_branch:
        plain(f"Already on profile '{name}'")
        return

    dotfiles = get_dotfiles_manager(config)
    if not dotfiles:
        error("Dotfiles not configured.")
        raise typer.Exit(1)

    plain(f"Comparing '{current_branch}' to '{name}' ({target_branch}):")
    plain("")

    try:
        # Get file differences
        result = dotfiles._git.run(
            "diff", "--stat", f"{current_branch}..{target_branch}"
        )

        if result.stdout.strip():
            plain(result.stdout)
        else:
            muted("No differences found.")

    except subprocess.CalledProcessError as e:
        error(f"Failed to diff: {get_subprocess_error(e)}")
        raise typer.Exit(1)
