"""Restore command for freckle CLI."""

from typing import List, Optional

import typer

from freckle.backup import BackupManager

from .helpers import env


def register(app: typer.Typer) -> None:
    """Register restore command with the app."""
    app.command()(restore)


def restore(
    identifier: Optional[str] = typer.Argument(
        None,
        help="Restore point (date or timestamp prefix, e.g. 2026-01-25)",
    ),
    files: Optional[List[str]] = typer.Option(
        None,
        "--file",
        "-f",
        help="Specific file(s) to restore (can be repeated)",
    ),
    list_points: bool = typer.Option(
        False,
        "--list",
        "-l",
        help="List available restore points",
    ),
    delete: Optional[str] = typer.Option(
        None,
        "--delete",
        help="Delete a restore point by identifier",
    ),
):
    """Restore files from a previous backup.

    Before destructive operations like sync or force-checkout, freckle
    automatically backs up affected files. Use this command to restore them.

    Examples:
        freckle restore --list                  # List available restore points
        freckle restore 2026-01-25              # Restore from date
        freckle restore 2026-01-25 -f .zshrc    # Restore specific file
        freckle restore --delete 2026-01-25    # Delete a restore point
    """
    manager = BackupManager()

    # Handle --list
    if list_points:
        points = manager.list_restore_points()

        if not points:
            typer.echo("No restore points available.")
            typer.echo(
                "\nRestore points are created automatically before "
                "sync or force-checkout."
            )
            return

        typer.echo("Available restore points:\n")
        for point in points:
            file_count = len(point.files)
            typer.echo(
                f"  {point.display_time} - {point.reason} ({file_count} files)"
            )

        typer.echo(
            f"\nTo restore: freckle restore <date>  (e.g. {points[0].timestamp[:10]})"  # noqa: E501
        )
        return

    # Handle --delete
    if delete:
        point = manager.get_restore_point(delete)
        if not point:
            typer.echo(f"Restore point not found: {delete}", err=True)
            raise typer.Exit(1)

        if manager.delete_restore_point(point):
            typer.echo(f"✓ Deleted restore point from {point.display_time}")
        else:
            typer.echo("Failed to delete restore point", err=True)
            raise typer.Exit(1)
        return

    # Restore requires identifier
    if not identifier:
        typer.echo("Usage: freckle restore <identifier>", err=True)
        typer.echo(
            "\nRun 'freckle restore --list' to see available restore points."
        )
        raise typer.Exit(1)

    # Find restore point
    point = manager.get_restore_point(identifier)
    if not point:
        typer.echo(f"Restore point not found: {identifier}", err=True)
        typer.echo(
            "\nRun 'freckle restore --list' to see available restore points."
        )
        raise typer.Exit(1)

    # Show what we're about to restore
    files_to_restore = files if files else point.files

    typer.echo(f"Restoring from {point.display_time} ({point.reason}):\n")

    # Validate requested files exist in restore point
    if files:
        missing = [f for f in files if f not in point.files]
        if missing:
            typer.echo("Warning: These files are not in the restore point:")
            for f in missing:
                typer.echo(f"  - {f}")
            typer.echo("")

        files_to_restore = [f for f in files if f in point.files]
        if not files_to_restore:
            typer.echo("No matching files to restore.", err=True)
            raise typer.Exit(1)

    for f in files_to_restore:
        typer.echo(f"  {f}")

    typer.echo("")

    # Confirm
    if not typer.confirm("Restore these files?"):
        typer.echo("Cancelled.")
        raise typer.Exit(0)

    # Do the restore
    restored = manager.restore(point, env.home, files_to_restore)

    if restored:
        typer.echo(f"\n✓ Restored {len(restored)} file(s):")
        for f in restored:
            typer.echo(f"    {f}")
    else:
        typer.echo("No files were restored.", err=True)
        raise typer.Exit(1)
