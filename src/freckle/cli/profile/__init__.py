"""Profile management commands for freckle CLI."""

from typing import List, Optional

import typer

from ..helpers import get_config
from .create import profile_create
from .delete import profile_delete
from .operations import (
    profile_diff,
    profile_list,
    profile_show,
    profile_switch,
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
    include: Optional[List[str]] = typer.Option(
        None,
        "--include", "-i",
        help="Profiles to inherit modules from (for create)",
    ),
    exclude: Optional[List[str]] = typer.Option(
        None,
        "--exclude", "-e",
        help="Modules to exclude from inherited profiles (for create)",
    ),
    modules: Optional[List[str]] = typer.Option(
        None,
        "--modules", "-m",
        help="Modules for the new profile (for create)",
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

    Profiles can inherit modules from other profiles using --include,
    and exclude specific modules using --exclude.

    Examples:
        freckle profile list              # List all profiles
        freckle profile show              # Show current profile
        freckle profile switch work       # Switch to 'work' profile
        freckle profile create laptop     # Create new profile
        freckle profile diff work         # Compare to 'work' profile

        # Create with inheritance:
        freckle profile create mac --include main --modules karabiner
        freckle profile create server --include main --exclude nvim,tmux
    """
    config = get_config()
    profiles = config.get_profiles()

    # Default to 'list' if no action
    if action is None:
        action = "list"

    if action == "list":
        profile_list(config, profiles)
    elif action == "show":
        profile_show(config, profiles)
    elif action == "switch":
        if not name:
            typer.echo("Usage: freckle profile switch <name>", err=True)
            raise typer.Exit(1)
        profile_switch(config, name, force)
    elif action == "create":
        if not name:
            typer.echo("Usage: freckle profile create <name>", err=True)
            raise typer.Exit(1)
        profile_create(
            config, name, from_profile, description, include, exclude, modules
        )
    elif action == "delete":
        if not name:
            typer.echo("Usage: freckle profile delete <name>", err=True)
            raise typer.Exit(1)
        profile_delete(config, name, force)
    elif action == "diff":
        if not name:
            typer.echo("Usage: freckle profile diff <name>", err=True)
            raise typer.Exit(1)
        profile_diff(config, name)
    else:
        typer.echo(f"Unknown action: {action}", err=True)
        typer.echo(
            "Valid actions: list, show, switch, create, delete, diff"
        )
        raise typer.Exit(1)
