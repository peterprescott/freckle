"""Git convenience commands for freckle CLI."""

import subprocess
from pathlib import Path
from typing import List, Optional

import typer

from .helpers import env, get_config, get_dotfiles_dir, get_dotfiles_manager


def register(app: typer.Typer) -> None:
    """Register git commands with the app."""
    app.command(name="changes")(changes)


def changes(
    files: Optional[List[str]] = typer.Argument(
        None, help="Specific files to show changes for"
    ),
    staged: bool = typer.Option(False, "--staged", help="Show staged changes"),
):
    """Show uncommitted changes in your dotfiles.

    Shows local changes that haven't been backed up yet.

    Examples:
        freckle changes              # Show all uncommitted changes
        freckle changes .zshrc       # Show changes to specific file
        freckle changes --staged     # Show staged changes
    """
    config = get_config()

    dotfiles = get_dotfiles_manager(config)
    if not dotfiles:
        typer.echo(
            "Dotfiles not configured. Run 'freckle init' first.", err=True
        )
        raise typer.Exit(1)

    dotfiles_dir = get_dotfiles_dir(config)

    if not dotfiles_dir.exists():
        typer.echo(
            "Dotfiles repository not found. Run 'freckle sync' first.",
            err=True,
        )
        raise typer.Exit(1)

    try:
        args = ["diff", "--color=always"]
        if staged:
            args.append("--staged")

        if files:
            # Convert paths to home-relative
            for f in files:
                path = Path(f).expanduser()
                if not path.is_absolute():
                    path = Path.cwd() / path
                path = path.resolve()
                try:
                    relative = path.relative_to(env.home)
                    args.append(str(relative))
                except ValueError:
                    args.append(f)

        result = dotfiles._git.run(*args)

        if result.stdout.strip():
            typer.echo("\nChanges not yet backed up:\n")
            typer.echo(result.stdout)
        else:
            if staged:
                typer.echo("No staged changes.")
            else:
                typer.echo("No uncommitted changes.")
    except subprocess.CalledProcessError as e:
        typer.echo(f"Error: {e.stderr}", err=True)
        raise typer.Exit(1)
