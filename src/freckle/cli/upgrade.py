"""Upgrade command for updating freckle itself."""

import subprocess

import typer

from ..utils import get_version


def register(app: typer.Typer) -> None:
    """Register the upgrade command with the app."""
    app.command()(upgrade)


def upgrade(
    force: bool = typer.Option(
        False, "--force", "-f", help="Upgrade even if already on latest"
    ),
):
    """Upgrade freckle to the latest version.

    Uses uv to upgrade the freckle package from PyPI.

    Example:
        freckle upgrade
    """
    typer.echo(f"Current version: {get_version()}")

    # Check if uv is available
    try:
        subprocess.run(
            ["uv", "--version"],
            check=True,
            capture_output=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        typer.echo(
            "Error: uv not found. Please upgrade manually with:",
            err=True,
        )
        typer.echo("  uv tool upgrade freckle", err=True)
        raise typer.Exit(1)

    typer.echo("Upgrading freckle...")

    try:
        result = subprocess.run(
            ["uv", "tool", "upgrade", "freckle"],
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            # Check if actually upgraded
            if "already installed" in result.stdout.lower():
                typer.echo("✓ Already on the latest version")
            else:
                typer.echo(result.stdout.strip())
                typer.echo("✓ Upgrade complete")
        else:
            typer.echo(f"Upgrade failed: {result.stderr.strip()}", err=True)
            raise typer.Exit(1)

    except Exception as e:
        typer.echo(f"Upgrade failed: {e}", err=True)
        raise typer.Exit(1)
