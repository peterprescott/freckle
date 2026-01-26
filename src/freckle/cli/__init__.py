"""Freckle CLI - Command-line interface for dotfiles management."""

import typer

from ..utils import get_version, setup_logging
from . import files, git, init, restore, schedule, status, sync, tools

# Create the main app
app = typer.Typer(
    name="freckle",
    help="Keep track of all your dot(file)s.",
    add_completion=True,
    no_args_is_help=True,
)


@app.callback()
def main_callback(
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose logging output.",
    ),
):
    """Freckle - dotfiles manager with tool installation."""
    setup_logging(verbose=verbose)


# Register all commands
init.register(app)
sync.register(app)
files.register(app)
status.register(app)
git.register(app)
restore.register(app)
schedule.register(app)
tools.register(app)


@app.command()
def version():
    """Show the version of freckle."""
    typer.echo(f"freckle version {get_version()}")


def main():
    """Main entry point for the freckle CLI."""
    app()
