"""Freckle CLI - Command-line interface for dotfiles management."""

import typer

from ..utils import setup_logging
from . import (
    config,
    doctor,
    fetch,
    files,
    git,
    history,
    init,
    profile,
    push,
    restore,
    save,
    schedule,
    status,
    tools,
    version,
)

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
save.register(app)
push.register(app)
fetch.register(app)
files.register(app)
status.register(app)
git.register(app)
history.register(app)
profile.register(app)
config.register(app)
restore.register(app)
schedule.register(app)
tools.register(app)
doctor.register(app)
version.register(app)


def main():
    """Main entry point for the freckle CLI."""
    app()
