"""Git convenience commands for freckle CLI."""

import subprocess
from pathlib import Path
from typing import List, Optional

import typer

from .helpers import env, get_config, require_dotfiles_ready
from .output import console, error, plain


def register(app: typer.Typer) -> None:
    """Register git commands with the app."""
    app.command(name="changes")(changes)


def changes(
    files: Optional[List[str]] = typer.Argument(
        None, help="Specific files to show changes for"
    ),
    staged: bool = typer.Option(False, "--staged", help="Show staged changes"),
) -> None:
    """Show uncommitted changes in your dotfiles.

    Shows local changes that haven't been backed up yet.

    Examples:
        freckle changes              # Show all uncommitted changes
        freckle changes .zshrc       # Show changes to specific file
        freckle changes --staged     # Show staged changes
    """
    config = get_config()
    dotfiles, _ = require_dotfiles_ready(config)

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
            plain("\nChanges not yet backed up:\n")
            console.print(result.stdout)
        else:
            if staged:
                plain("No staged changes.")
            else:
                plain("No uncommitted changes.")
    except subprocess.CalledProcessError as e:
        error(f"{e.stderr}")
        raise typer.Exit(1)
