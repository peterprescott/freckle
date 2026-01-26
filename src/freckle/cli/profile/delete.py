"""Profile deletion functionality."""

import subprocess

import typer
import yaml

from ..helpers import (
    CONFIG_FILENAME,
    CONFIG_PATH,
    get_dotfiles_manager,
    get_subprocess_error,
)
from .helpers import get_current_branch


def remove_profile_from_config(name: str):
    """Remove a profile from the config file."""
    # Read current config
    with open(CONFIG_PATH, "r") as f:
        data = yaml.safe_load(f) or {}

    # Remove profile if it exists
    if "profiles" in data and name in data["profiles"]:
        del data["profiles"][name]

    # Write back
    with open(CONFIG_PATH, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def profile_delete(config, name, force):
    """Delete a profile."""
    profiles = config.get_profiles()

    if name not in profiles:
        typer.echo(f"Profile not found: {name}", err=True)
        raise typer.Exit(1)

    current_branch = get_current_branch(config=config)
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
        # Step 1: Delete the branch
        dotfiles._git.run("branch", "-D", target_branch)
        typer.echo(f"✓ Deleted branch '{target_branch}'")

        # Step 2: Remove profile from config
        remove_profile_from_config(name)
        typer.echo(f"✓ Removed '{name}' from {CONFIG_FILENAME}")

        # Step 3: Commit the config change
        dotfiles._git.run("add", str(CONFIG_PATH))
        try:
            dotfiles._git.run("commit", "-m", f"Remove profile: {name}")
            typer.echo("✓ Committed config change")
        except subprocess.CalledProcessError:
            typer.echo("  (config already committed)")

        # Step 4: Propagate to other branches
        config_content = CONFIG_PATH.read_text()
        remaining_profiles = config.get_profiles()
        # Remove the deleted profile from our list
        remaining_profiles.pop(name, None)

        other_branches = [
            p for p in remaining_profiles.keys()
            if p != current_branch
        ]

        if other_branches:
            n = len(other_branches)
            typer.echo(f"Syncing config to {n} branch(es)...")
            for branch in other_branches:
                try:
                    dotfiles._git.run("checkout", branch)
                    CONFIG_PATH.write_text(config_content)
                    dotfiles._git.run("add", str(CONFIG_PATH))
                    try:
                        dotfiles._git.run(
                            "commit", "-m", f"Remove profile: {name}"
                        )
                        typer.echo(f"  ✓ {branch}")
                    except subprocess.CalledProcessError:
                        typer.echo(f"  ✓ {branch} (already synced)")
                except subprocess.CalledProcessError:
                    typer.echo(f"  ✗ {branch} (failed)")

            # Return to original branch
            dotfiles._git.run("checkout", current_branch)

        typer.echo(f"\n✓ Profile '{name}' deleted")

    except subprocess.CalledProcessError as e:
        typer.echo(f"Failed to delete: {get_subprocess_error(e)}", err=True)
        raise typer.Exit(1)
