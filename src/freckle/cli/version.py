"""Version commands for freckle CLI."""

import subprocess
from typing import Optional

import typer

from ..utils import get_version
from .output import console, error, muted, plain, success, warning

# Create version sub-app
version_app = typer.Typer(
    name="version",
    help="Show version and manage upgrades.",
    no_args_is_help=False,
)


def register(app: typer.Typer) -> None:
    """Register version command group with the app."""
    app.add_typer(version_app, name="version")


def get_latest_version_from_pypi() -> Optional[str]:
    """Get the latest version of freckle from PyPI."""
    try:
        result = subprocess.run(
            ["uv", "pip", "show", "freckle", "--quiet"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        # This gets installed version, not latest. Try another approach.
    except Exception:
        pass

    # Use pip index to get latest version
    try:
        result = subprocess.run(
            [
                "python",
                "-c",
                "import urllib.request, json; "
                "data = json.loads(urllib.request.urlopen("
                "'https://pypi.org/pypi/freckle/json', timeout=5"
                ").read()); "
                "print(data['info']['version'])",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass

    return None


def parse_version(version_str: str) -> tuple:
    """Parse a version string into a comparable tuple."""
    # Remove any leading 'v' and development markers
    version_str = version_str.lstrip("v").split("-")[0].split("+")[0]
    try:
        parts = version_str.split(".")
        return tuple(int(p) for p in parts[:3])
    except (ValueError, IndexError):
        return (0, 0, 0)


def is_version_lower(current: str, latest: str) -> bool:
    """Check if current version is lower than latest."""
    return parse_version(current) < parse_version(latest)


@version_app.callback(invoke_without_command=True)
def version_callback(ctx: typer.Context):
    """Show the current version of freckle.

    Use 'freckle version upgrade' to update to the latest version.
    """
    if ctx.invoked_subcommand is None:
        show_version()


def show_version():
    """Show current and latest version information."""
    current = get_version()
    plain(f"freckle version {current}")

    # Check for latest version
    latest = get_latest_version_from_pypi()
    if latest and latest != current:
        if is_version_lower(current, latest):
            warning(f"Update available: {latest}")
            muted("Run 'freckle version upgrade' to update.")


@version_app.command(name="upgrade")
def version_upgrade(
    force: bool = typer.Option(
        False, "--force", "-f", help="Upgrade even if already on latest"
    ),
):
    """Upgrade freckle to the latest version.

    Uses uv to upgrade the freckle package from PyPI.

    Example:
        freckle version upgrade
    """
    current = get_version()
    plain(f"Current version: {current}")

    # Check latest version first
    plain("Checking for updates...")
    latest = get_latest_version_from_pypi()

    if latest:
        plain(f"Latest version:  {latest}")

        if not force and not is_version_lower(current, latest):
            success("Already on the latest version")
            return
    else:
        plain("Could not check latest version, proceeding...")

    # Check if uv is available
    try:
        subprocess.run(
            ["uv", "--version"],
            check=True,
            capture_output=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        error("uv not found. Please upgrade manually with:")
        muted("  uv tool upgrade freckle")
        raise typer.Exit(1)

    plain("\nUpgrading freckle...")

    try:
        result = subprocess.run(
            ["uv", "tool", "upgrade", "freckle"],
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            # Get new version after upgrade
            new_version = get_version()

            if "already" in result.stdout.lower():
                success("Already on the latest version")
            else:
                plain(result.stdout.strip())
                console.print(
                    f"\n[bold green]✓ Upgraded to {new_version}[/bold green]"
                )
        else:
            error(f"Upgrade failed: {result.stderr.strip()}")
            raise typer.Exit(1)

    except subprocess.CalledProcessError as e:
        error(f"Upgrade failed: {e}")
        raise typer.Exit(1)


@version_app.command(name="check")
def version_check():
    """Check if a newer version is available.

    Example:
        freckle version check
    """
    current = get_version()
    plain(f"Current version: {current}")

    plain("Checking for updates...")
    latest = get_latest_version_from_pypi()

    if latest is None:
        error("Could not check latest version (offline?)")
        raise typer.Exit(1)

    plain(f"Latest version:  {latest}")

    if is_version_lower(current, latest):
        console.print(
            f"\n[bold yellow]↑ Update: {current} → {latest}[/bold yellow]"
        )
        muted("Run 'freckle version upgrade' to update.")
    else:
        success("You are on the latest version")
