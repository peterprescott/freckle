"""Profile creation functionality."""

import subprocess

import typer
import yaml

from ..helpers import (
    CONFIG_FILENAME,
    CONFIG_PATH,
    get_dotfiles_dir,
    get_dotfiles_manager,
    get_subprocess_error,
)
from .helpers import get_current_branch


def add_profile_to_config(name: str, description: str, modules: list):
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


def profile_create(config, name, from_profile, description):
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
        current = get_current_branch(config=config, dotfiles=dotfiles)
        current = current or "main"
        source_branch = current
        if current in profiles:
            source_modules = profiles[current].get("modules", [])
        else:
            source_modules = []

    typer.echo(f"Creating profile '{name}' from '{source_branch}'...")

    original_branch = get_current_branch(config=config, dotfiles=dotfiles)

    try:
        # Step 1: Update config on current branch
        add_profile_to_config(name, description, source_modules)
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
                    failed_branches.append((branch, get_subprocess_error(e)))
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

        # Step 5: Push the new branch to remote
        try:
            dotfiles._git.run_bare(
                "push", "-u", "origin", name, check=True, timeout=60
            )
            typer.echo(f"✓ Pushed branch '{name}' to origin")
        except subprocess.CalledProcessError:
            typer.echo(
                f"⚠ Could not push to origin/{name}. "
                "Run 'freckle save' to push later."
            )

        typer.echo(f"\n✓ Profile '{name}' created")

    except subprocess.CalledProcessError as e:
        typer.echo(
            f"Failed to create profile: {get_subprocess_error(e)}", err=True
        )

        # Try to return to original branch
        if original_branch:
            try:
                dotfiles._git.run("checkout", original_branch)
            except subprocess.CalledProcessError:
                pass  # Best effort

        raise typer.Exit(1)
