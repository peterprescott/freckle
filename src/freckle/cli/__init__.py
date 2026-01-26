"""Freckle CLI - Command-line interface for dotfiles management."""

import typer

from ..utils import get_version, setup_logging
from . import files, git, init, schedule, status, sync

# Create the main app
app = typer.Typer(
    name="freckle",
    help="Keep track of all your dot(file)s. A dotfiles manager with tool installation.",
    add_completion=True,
    no_args_is_help=True,
)

# Register all commands
init.register(app)
sync.register(app)
files.register(app)
status.register(app)
git.register(app)
schedule.register(app)


@app.command()
def version():
    """Show the version of freckle."""
    typer.echo(f"freckle version {get_version()}")


def main():
    """Main entry point for the freckle CLI."""
    setup_logging()
    app()
