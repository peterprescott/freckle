"""Profile operations: list, show, switch, diff."""

import subprocess
from typing import List

import typer

from ..helpers import (
    CONFIG_FILENAME,
    env,
    get_dotfiles_dir,
    get_dotfiles_manager,
    get_subprocess_error,
)
from ..output import console, error, muted, plain, success, warning
from .helpers import get_current_branch


def _get_local_branches(dotfiles) -> List[str]:
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


def profile_list(config, profiles):
    """List all profiles.

    Shows profiles from config AND branches (branches are authoritative).
    Branches without config entries are shown as implicit profiles.
    """
    dotfiles = get_dotfiles_manager(config)
    current_branch = get_current_branch(config=config)

    # Get all local branches (authoritative)
    local_branches = _get_local_branches(dotfiles) if dotfiles else []

    # Merge: config profiles + implicit profiles from branches
    all_profiles = dict(profiles)
    implicit_branches = []
    for branch in local_branches:
        if branch not in all_profiles:
            implicit_branches.append(branch)
            all_profiles[branch] = {"_implicit": True, "modules": []}

    if not all_profiles:
        plain("No profiles configured.")
        muted(f"\nTo create a profile, add to {CONFIG_FILENAME}:")
        muted("  profiles:")
        muted("    main:")
        muted('      description: "My main config"')
        muted("      modules: [zsh, nvim]")
        return

    plain("Available profiles:\n")
    for name, profile in all_profiles.items():
        branch = name  # Profile name = branch name
        is_implicit = profile.get("_implicit", False)
        desc = profile.get("description", "")
        includes = profile.get("include", [])
        excludes = profile.get("exclude", [])
        own_modules = profile.get("modules", [])

        is_current = current_branch == branch

        if is_current:
            if is_implicit:
                console.print(
                    f"  [green]*[/green] [bold]{name}[/bold] "
                    "[dim](branch only)[/dim]"
                )
            else:
                console.print(f"  [green]*[/green] [bold]{name}[/bold]")
        else:
            if is_implicit:
                console.print(f"    {name} [dim](branch only)[/dim]")
            else:
                plain(f"    {name}")

        if is_implicit:
            muted("      not in config - run 'freckle doctor' to fix")
            continue

        if desc:
            muted(f"      {desc}")
        if includes:
            muted(f"      includes: {', '.join(includes)}")
        if excludes:
            muted(f"      excludes: {', '.join(excludes)}")
        if own_modules:
            if includes:
                muted(f"      own modules: {', '.join(own_modules)}")
            else:
                muted(f"      modules: {', '.join(own_modules)}")
        # Show resolved modules if there's inheritance
        if includes:
            resolved = config.get_profile_modules(name)
            muted(f"      resolved: {', '.join(resolved)}")
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

        includes = profile.get("include", [])
        excludes = profile.get("exclude", [])
        own_modules = profile.get("modules", [])

        if includes:
            muted(f"  Includes: {', '.join(includes)}")
        if excludes:
            muted(f"  Excludes: {', '.join(excludes)}")
        if own_modules:
            if includes:
                muted(f"  Own modules: {', '.join(own_modules)}")
            else:
                muted(f"  Modules: {', '.join(own_modules)}")

        # Show resolved modules if there's inheritance
        if includes:
            resolved = config.get_profile_modules(current_profile)
            muted(f"  Resolved modules: {', '.join(resolved)}")
    else:
        plain(f"Current branch: {current_branch}")
        muted("  (not matching any defined profile)")


def profile_switch(config, name, force):
    """Switch to a different profile.

    Branches are authoritative: if a branch exists, you can switch to it
    even if it's not defined in the config file.
    """
    profiles = config.get_profiles()
    target_branch = name  # Profile name = branch name

    dotfiles = get_dotfiles_manager(config)
    if not dotfiles:
        error("Dotfiles not configured.")
        raise typer.Exit(1)

    dotfiles_dir = get_dotfiles_dir(config)
    if not dotfiles_dir.exists():
        error("Dotfiles repository not found.")
        raise typer.Exit(1)

    # Get all local branches (authoritative for profile existence)
    local_branches = _get_local_branches(dotfiles)
    is_in_config = name in profiles
    is_valid_branch = name in local_branches

    if not is_in_config and not is_valid_branch:
        error(f"Profile not found: {name}")
        plain("\nAvailable profiles/branches:")
        # Show config profiles
        for p in profiles:
            if p in local_branches:
                muted(f"  - {p}")
            else:
                muted(f"  - {p} (no branch)")
        # Show branches not in config
        for b in local_branches:
            if b not in profiles:
                muted(f"  - {b} (branch only)")
        raise typer.Exit(1)

    if not is_in_config and is_valid_branch:
        # Branch exists but not in config - warn but allow
        warning(f"Branch '{name}' exists but is not in config")
        muted("  Run 'freckle doctor' to add it to config")

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

        # Show resolved modules for this profile (only if in config)
        if is_in_config:
            resolved_modules = config.get_profile_modules(name)
            if resolved_modules:
                muted(f"  Modules: {', '.join(resolved_modules)}")

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
