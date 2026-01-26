"""Profile management commands for freckle CLI."""

import subprocess
from typing import List, Optional

import typer
import yaml

from .helpers import (
    CONFIG_FILENAME,
    CONFIG_PATH,
    env,
    get_config,
    get_dotfiles_dir,
    get_dotfiles_manager,
)


def _complete_profile_action(incomplete: str) -> List[str]:
    """Autocomplete profile actions."""
    actions = ["list", "show", "switch", "create", "delete", "diff"]
    return [a for a in actions if a.startswith(incomplete)]


def _complete_profile_name(incomplete: str) -> List[str]:
    """Autocomplete profile names from config."""
    try:
        config = get_config()
        profiles = config.get_profiles()
        return [p for p in profiles.keys() if p.startswith(incomplete)]
    except Exception:
        return []


def register(app: typer.Typer) -> None:
    """Register profile commands with the app."""
    app.command()(profile)


def profile(
    action: Optional[str] = typer.Argument(
        None,
        help="Action: list, show, switch, create, delete, diff",
        autocompletion=_complete_profile_action,
    ),
    name: Optional[str] = typer.Argument(
        None,
        help="Profile name (for switch, create, delete, diff)",
        autocompletion=_complete_profile_name,
    ),
    from_profile: Optional[str] = typer.Option(
        None,
        "--from",
        help="Source profile for create",
        autocompletion=_complete_profile_name,
    ),
    description: Optional[str] = typer.Option(
        None,
        "--description", "-d",
        help="Description for new profile",
    ),
    force: bool = typer.Option(
        False,
        "--force", "-f",
        help="Force action (skip confirmations)",
    ),
):
    """Manage dotfiles profiles.

    Profiles allow different configurations for different machines.
    Each profile corresponds to a git branch.

    Examples:
        freckle profile list              # List all profiles
        freckle profile show              # Show current profile
        freckle profile switch work       # Switch to 'work' profile
        freckle profile create laptop     # Create new profile
        freckle profile diff work         # Compare to 'work' profile
    """
    config = get_config()
    profiles = config.get_profiles()

    # Default to 'list' if no action
    if action is None:
        action = "list"

    if action == "list":
        _profile_list(config, profiles)
    elif action == "show":
        _profile_show(config, profiles)
    elif action == "switch":
        if not name:
            typer.echo("Usage: freckle profile switch <name>", err=True)
            raise typer.Exit(1)
        _profile_switch(config, name, force)
    elif action == "create":
        if not name:
            typer.echo("Usage: freckle profile create <name>", err=True)
            raise typer.Exit(1)
        _profile_create(config, name, from_profile, description)
    elif action == "delete":
        if not name:
            typer.echo("Usage: freckle profile delete <name>", err=True)
            raise typer.Exit(1)
        _profile_delete(config, name, force)
    elif action == "diff":
        if not name:
            typer.echo("Usage: freckle profile diff <name>", err=True)
            raise typer.Exit(1)
        _profile_diff(config, name)
    else:
        typer.echo(f"Unknown action: {action}", err=True)
        typer.echo(
            "Valid actions: list, show, switch, create, delete, diff"
        )
        raise typer.Exit(1)


def _get_current_branch() -> Optional[str]:
    """Get the current git branch for dotfiles."""
    config = get_config()
    dotfiles = get_dotfiles_manager(config)
    if not dotfiles:
        return None

    dotfiles_dir = get_dotfiles_dir(config)
    if not dotfiles_dir.exists():
        return None

    try:
        result = dotfiles._git.run("rev-parse", "--abbrev-ref", "HEAD")
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None


def _profile_list(config, profiles):
    """List all profiles."""
    if not profiles:
        typer.echo("No profiles configured.")
        typer.echo(f"\nTo create a profile, add to {CONFIG_FILENAME}:")
        typer.echo("  profiles:")
        typer.echo("    main:")
        typer.echo('      description: "My main config"')
        typer.echo("      modules: [zsh, nvim]")
        return

    current_branch = _get_current_branch()

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


def _profile_show(config, profiles):
    """Show current profile details."""
    current_branch = _get_current_branch()

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


def _profile_switch(config, name, force):
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
        stderr = getattr(e, "stderr", "")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        typer.echo(f"Failed to switch: {stderr.strip()}", err=True)
        raise typer.Exit(1)


def _profile_create(config, name, from_profile, description):
    """Create a new profile."""
    profiles = config.get_profiles()

    if name in profiles:
        typer.echo(f"Profile already exists: {name}", err=True)
        raise typer.Exit(1)

    dotfiles = get_dotfiles_manager(config)
    if not dotfiles:
        typer.echo("Dotfiles not configured.", err=True)
        raise typer.Exit(1)

    dotfiles_dir = get_dotfiles_dir(config)
    if not dotfiles_dir.exists():
        typer.echo("Dotfiles repository not found.", err=True)
        raise typer.Exit(1)

    # Check if branch already exists (even if profile doesn't)
    try:
        result = dotfiles._git.run("branch", "--list", name)
        if result.stdout.strip():
            typer.echo(
                f"Branch '{name}' already exists. "
                "Delete it first or use a different name.",
                err=True,
            )
            raise typer.Exit(1)
    except subprocess.CalledProcessError:
        pass  # OK, branch doesn't exist

    # Determine source profile and branch
    if from_profile:
        if from_profile not in profiles:
            typer.echo(f"Source profile not found: {from_profile}", err=True)
            raise typer.Exit(1)
        source_branch = from_profile  # Profile name = branch name
        source_modules = profiles[from_profile].get("modules", [])
    else:
        # Use current branch/profile
        current = _get_current_branch() or "main"
        source_branch = current
        if current in profiles:
            source_modules = profiles[current].get("modules", [])
        else:
            source_modules = []

    typer.echo(f"Creating profile '{name}' from '{source_branch}'...")

    original_branch = _get_current_branch()

    try:
        # Step 1: Update config on current branch
        _add_profile_to_config(name, description, source_modules)
        typer.echo(f"✓ Added profile to {CONFIG_FILENAME}")

        # Step 2: Commit the config change
        dotfiles._git.run("add", str(CONFIG_PATH))
        try:
            dotfiles._git.run("commit", "-m", f"Add profile: {name}")
            typer.echo("✓ Committed config change")
        except subprocess.CalledProcessError:
            # Config might be unchanged (already committed)
            typer.echo("  (config already committed)")

        # Step 3: Create new branch
        dotfiles._git.run("checkout", "-b", name)
        typer.echo(f"✓ Created branch '{name}'")

        # Step 4: Propagate config to ALL other profile branches
        config_content = CONFIG_PATH.read_text()

        # Get all other branches that need updating
        other_branches = []
        for profile_name in profiles.keys():
            branch = profile_name  # Profile name = branch name
            if branch != name and branch != source_branch:
                other_branches.append(branch)

        if other_branches:
            n = len(other_branches)
            typer.echo(f"Syncing config to {n} other branch(es)...")
            failed_branches = []
            for branch in other_branches:
                try:
                    dotfiles._git.run("checkout", branch)
                    CONFIG_PATH.write_text(config_content)
                    dotfiles._git.run("add", str(CONFIG_PATH))
                    try:
                        dotfiles._git.run(
                            "commit", "-m", f"Add profile: {name}"
                        )
                        typer.echo(f"  ✓ {branch}")
                    except subprocess.CalledProcessError:
                        # Already has this content
                        typer.echo(f"  ✓ {branch} (already synced)")
                except subprocess.CalledProcessError as e:
                    stderr = getattr(e, "stderr", "")
                    if isinstance(stderr, bytes):
                        stderr = stderr.decode("utf-8", errors="replace")
                    failed_branches.append((branch, stderr.strip()))
                    typer.echo(f"  ✗ {branch} (failed)")

            # Return to the new profile branch
            try:
                dotfiles._git.run("checkout", name)
            except subprocess.CalledProcessError:
                typer.echo(
                    f"Warning: could not return to branch '{name}'",
                    err=True
                )

            if failed_branches:
                typer.echo(
                    f"\n⚠ {len(failed_branches)} branch(es) failed to sync. "
                    "Run 'freckle config propagate' later."
                )

        typer.echo(f"\n✓ Profile '{name}' created")

    except subprocess.CalledProcessError as e:
        stderr = getattr(e, "stderr", "")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        typer.echo(f"Failed to create profile: {stderr}", err=True)

        # Try to return to original branch
        if original_branch:
            try:
                dotfiles._git.run("checkout", original_branch)
            except subprocess.CalledProcessError:
                pass  # Best effort

        raise typer.Exit(1)


def _add_profile_to_config(name: str, description: str, modules: list):
    """Add a new profile to the config file."""
    # Read current config
    with open(CONFIG_PATH, "r") as f:
        data = yaml.safe_load(f) or {}

    # Ensure profiles section exists
    if "profiles" not in data:
        data["profiles"] = {}

    # Add new profile
    new_profile = {"modules": modules}
    if description:
        new_profile["description"] = description

    data["profiles"][name] = new_profile

    # Write back
    with open(CONFIG_PATH, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def _profile_delete(config, name, force):
    """Delete a profile."""
    profiles = config.get_profiles()

    if name not in profiles:
        typer.echo(f"Profile not found: {name}", err=True)
        raise typer.Exit(1)

    current_branch = _get_current_branch()
    target_branch = name  # Profile name = branch name

    if current_branch == target_branch:
        typer.echo(
            "Cannot delete current profile. "
            "Switch to another profile first.",
            err=True,
        )
        raise typer.Exit(1)

    if not force:
        if not typer.confirm(
            f"Delete profile '{name}' and branch '{target_branch}'?"
        ):
            typer.echo("Cancelled.")
            return

    dotfiles = get_dotfiles_manager(config)
    if not dotfiles:
        typer.echo("Dotfiles not configured.", err=True)
        raise typer.Exit(1)

    try:
        dotfiles._git.run("branch", "-D", target_branch)
        typer.echo(f"✓ Deleted branch '{target_branch}'")

        typer.echo(
            f"\nRemember to remove '{name}' from profiles in {CONFIG_FILENAME}"
        )
        typer.echo("Then run 'freckle config propagate' to sync config.")

    except subprocess.CalledProcessError as e:
        stderr = getattr(e, "stderr", "")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        typer.echo(f"Failed to delete: {stderr.strip()}", err=True)
        raise typer.Exit(1)


def _profile_diff(config, name):
    """Show diff between current profile and another."""
    profiles = config.get_profiles()

    if name not in profiles:
        typer.echo(f"Profile not found: {name}", err=True)
        raise typer.Exit(1)

    current_branch = _get_current_branch()
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
        stderr = getattr(e, "stderr", "")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        typer.echo(f"Failed to diff: {stderr.strip()}", err=True)
        raise typer.Exit(1)
