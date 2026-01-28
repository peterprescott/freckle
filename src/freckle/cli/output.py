"""Standardized colorized output utilities for freckle CLI.

Uses Rich for terminal formatting. Respects NO_COLOR environment variable.
"""

import os
import sys

from rich.console import Console

# Respect NO_COLOR environment variable (https://no-color.org/)
# Also disable colors when not connected to a terminal (piping)
_force_terminal = None
if os.environ.get("NO_COLOR") is not None:
    _force_terminal = False

console = Console(force_terminal=_force_terminal, highlight=False)
err_console = Console(
    force_terminal=_force_terminal, stderr=True, highlight=False
)


def success(message: str, prefix: str = "✓") -> None:
    """Print a success message in green."""
    console.print(f"[green]{prefix}[/green] {message}")


def error(message: str, prefix: str = "✗") -> None:
    """Print an error message in red to stderr."""
    err_console.print(f"[red]{prefix}[/red] {message}")


def warning(message: str, prefix: str = "⚠") -> None:
    """Print a warning message in yellow."""
    console.print(f"[yellow]{prefix}[/yellow] {message}")


def info(message: str) -> None:
    """Print an info message in cyan."""
    console.print(f"[cyan]{message}[/cyan]")


def muted(message: str) -> None:
    """Print a muted/secondary message in dim text."""
    console.print(f"[dim]{message}[/dim]")


def plain(message: str) -> None:
    """Print a plain message without any styling."""
    console.print(message)


def plain_err(message: str) -> None:
    """Print a plain message to stderr without any styling."""
    err_console.print(message)


def status_line(label: str, value: str, ok: bool = True) -> None:
    """Print a status line with colored indicator.

    Example: ✓ .freckle.yaml: up-to-date
    """
    if ok:
        console.print(f"  [green]✓[/green] {label}: {value}")
    else:
        console.print(f"  [red]✗[/red] {label}: {value}")


def header(text: str) -> None:
    """Print a section header in bold."""
    console.print(f"\n[bold]{text}[/bold]")


def item(message: str, indent: int = 4) -> None:
    """Print an indented list item."""
    spaces = " " * indent
    console.print(f"{spaces}{message}")


def diff_add(line: str) -> None:
    """Print a diff addition line in green."""
    console.print(f"[green]{line}[/green]")


def diff_remove(line: str) -> None:
    """Print a diff removal line in red."""
    console.print(f"[red]{line}[/red]")


def diff_context(line: str) -> None:
    """Print a diff context line in dim text."""
    console.print(f"[dim]{line}[/dim]")


def commit_hash(short_hash: str) -> str:
    """Return a styled commit hash (for inline use)."""
    if _should_colorize():
        return f"[yellow]{short_hash}[/yellow]"
    return short_hash


def _should_colorize() -> bool:
    """Check if we should use colors."""
    if os.environ.get("NO_COLOR") is not None:
        return False
    return sys.stdout.isatty()
