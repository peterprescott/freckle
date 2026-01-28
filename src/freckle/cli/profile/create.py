"""Profile creation functionality."""

import subprocess
from typing import List, Optional

import typer
import yaml

from ..helpers import (
    CONFIG_FILENAME,
    CONFIG_PATH,
    get_dotfiles_dir,
    get_dotfiles_manager,
    get_subprocess_error,
)
from ..output import error, muted, plain, success, warning
from .helpers import get_current_branch


def add_profile_to_config(
    name: str,
    description: str,
    modules: List[str],
    include: Optional[List[str]] = None,
    exclude: Optional[List[str]] = None,
):
    """Add a new profile to the config file."""
    # Read current config
    with open(CONFIG_PATH, "r") as f:
        data = yaml.safe_load(f) or {}

    # Ensure profiles section exists
    if "profiles" not in data:
        data["profiles"] = {}

    # Add new profile - order keys for readability
    new_profile = {}
    if description:
        new_profile["description"] = description
    if include:
        new_profile["include"] = include
    if exclude:
        new_profile["exclude"] = exclude
    new_profile["modules"] = modules

    data["profiles"][name] = new_profile

    # Write back
    with open(CONFIG_PATH, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def profile_create(
    config,
    name,
    from_profile,
    description,
    include=None,
    exclude=None,
    modules=None,
):
    """Create a new profile.

    Args:
        config: The freckle Config object
        name: Name for the new profile
        from_profile: Optional profile to copy settings from
        description: Optional description for the profile
        include: Optional list of profiles to inherit from
        exclude: Optional list of modules to exclude from inherited
        modules: Optional list of modules (overrides from_profile modules)
    """
    profiles = config.get_profiles()

    if name in profiles:
        error(f"Profile already exists: {name}")
        raise typer.Exit(1)

    dotfiles = get_dotfiles_manager(config)
    if not dotfiles:
        error("Dotfiles not configured.")
        raise typer.Exit(1)

    dotfiles_dir = get_dotfiles_dir(config)
    if not dotfiles_dir.exists():
        error("Dotfiles repository not found.")
        raise typer.Exit(1)

    # Check if branch already exists (even if profile doesn't)
    try:
        result = dotfiles._git.run("branch", "--list", name)
        if result.stdout.strip():
            error(
                f"Branch '{name}' already exists. "
                "Delete it first or use a different name."
            )
            raise typer.Exit(1)
    except subprocess.CalledProcessError:
        pass  # OK, branch doesn't exist

    # Validate include references
    if include:
        for inc in include:
            if inc not in profiles:
                error(f"Cannot include unknown profile: {inc}")
                raise typer.Exit(1)
            if inc == name:
                error("Profile cannot include itself")
                raise typer.Exit(1)

    # Determine source profile and branch
    if from_profile:
        if from_profile not in profiles:
            error(f"Source profile not found: {from_profile}")
            raise typer.Exit(1)
        source_branch = from_profile  # Profile name = branch name
        source_profile = profiles[from_profile]
        # Copy include/exclude/modules from source if not explicitly provided
        if include is None:
            include = source_profile.get("include", [])
        if exclude is None:
            exclude = source_profile.get("exclude", [])
        if modules is None:
            modules = source_profile.get("modules", [])
    else:
        # Use current branch/profile
        current = get_current_branch(config=config, dotfiles=dotfiles)
        current = current or "main"
        source_branch = current
        if modules is None:
            if current in profiles:
                modules = profiles[current].get("modules", [])
            else:
                modules = []

    # Default to empty lists if still None
    include = include or []
    exclude = exclude or []
    modules = modules or []

    plain(f"Creating profile '{name}' from '{source_branch}'...")

    original_branch = get_current_branch(config=config, dotfiles=dotfiles)

    try:
        # Step 1: Update config on current branch
        add_profile_to_config(name, description, modules, include, exclude)
        success(f"Added profile to {CONFIG_FILENAME}")

        # Step 2: Commit the config change
        dotfiles._git.run("add", str(CONFIG_PATH))
        try:
            dotfiles._git.run("commit", "-m", f"Add profile: {name}")
            success("Committed config change")
        except subprocess.CalledProcessError:
            # Config might be unchanged (already committed)
            muted("  (config already committed)")

        # Step 3: Create new branch
        dotfiles._git.run("checkout", "-b", name)
        success(f"Created branch '{name}'")

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
            plain(f"Syncing config to {n} other branch(es)...")
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
                        success(branch, prefix="  ✓")
                    except subprocess.CalledProcessError:
                        # Already has this content
                        success(f"{branch} (already synced)", prefix="  ✓")
                except subprocess.CalledProcessError as e:
                    failed_branches.append((branch, get_subprocess_error(e)))
                    error(f"{branch} (failed)", prefix="  ✗")

            # Return to the new profile branch
            try:
                dotfiles._git.run("checkout", name)
            except subprocess.CalledProcessError:
                warning(f"Could not return to branch '{name}'")

            if failed_branches:
                warning(
                    f"{len(failed_branches)} branch(es) failed to sync. "
                    "Run 'freckle config propagate' later."
                )

        # Step 5: Push the new branch to remote
        try:
            dotfiles._git.run_bare(
                "push", "-u", "origin", name, check=True, timeout=60
            )
            success(f"Pushed branch '{name}' to origin")
        except subprocess.CalledProcessError:
            warning(
                f"Could not push to origin/{name}. "
                "Run 'freckle save' to push later."
            )

        success(f"Profile '{name}' created")

    except subprocess.CalledProcessError as e:
        error(f"Failed to create profile: {get_subprocess_error(e)}")

        # Try to return to original branch
        if original_branch:
            try:
                dotfiles._git.run("checkout", original_branch)
            except subprocess.CalledProcessError:
                pass  # Best effort

        raise typer.Exit(1)
