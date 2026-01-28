"""Schedule command for automatic saves."""

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

import typer

from .helpers import env
from .output import error, header, muted, plain, success

LAUNCHD_PLIST_PATH = (
    Path.home() / "Library/LaunchAgents/com.freckle.save.plist"
)
CRON_MARKER = "# freckle-save"


def register(app: typer.Typer) -> None:
    """Register the schedule command with the app."""
    app.command()(schedule)


def _get_freckle_path() -> str:
    """Get the path to the freckle executable."""
    freckle_path = shutil.which("freckle")
    if freckle_path:
        return freckle_path
    # Fallback to python -m freckle
    return f"{sys.executable} -m freckle"


def _create_launchd_plist(hour: int, minute: int, daily: bool = True) -> str:
    """Create a launchd plist for scheduled saves."""
    freckle_path = _get_freckle_path()

    # Handle python -m freckle case
    if " -m " in freckle_path:
        parts = freckle_path.split()
        program_args = f"""<array>
        <string>{parts[0]}</string>
        <string>-m</string>
        <string>freckle</string>
        <string>save</string>
        <string>--quiet</string>
        <string>--scheduled</string>
    </array>"""
    else:
        program_args = f"""<array>
        <string>{freckle_path}</string>
        <string>save</string>
        <string>--quiet</string>
        <string>--scheduled</string>
    </array>"""

    if daily:
        interval = f"""<key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>{hour}</integer>
        <key>Minute</key>
        <integer>{minute}</integer>
    </dict>"""
    else:
        # Weekly (Sunday)
        interval = f"""<key>StartCalendarInterval</key>
    <dict>
        <key>Weekday</key>
        <integer>0</integer>
        <key>Hour</key>
        <integer>{hour}</integer>
        <key>Minute</key>
        <integer>{minute}</integer>
    </dict>"""

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.freckle.save</string>
    <key>ProgramArguments</key>
    {program_args}
    {interval}
    <key>StandardOutPath</key>
    <string>/tmp/freckle-save.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/freckle-save.log</string>
    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
"""


def _install_launchd(hour: int, minute: int, daily: bool = True) -> bool:
    """Install launchd plist for macOS scheduled saves."""
    # Create LaunchAgents directory if needed
    LAUNCHD_PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Unload existing if present
    if LAUNCHD_PLIST_PATH.exists():
        subprocess.run(
            ["launchctl", "unload", str(LAUNCHD_PLIST_PATH)],
            capture_output=True,
        )

    # Write plist
    plist_content = _create_launchd_plist(hour, minute, daily)
    LAUNCHD_PLIST_PATH.write_text(plist_content)

    # Load it
    result = subprocess.run(
        ["launchctl", "load", str(LAUNCHD_PLIST_PATH)],
        capture_output=True,
        text=True,
    )

    return result.returncode == 0


def _uninstall_launchd() -> bool:
    """Remove launchd plist."""
    if not LAUNCHD_PLIST_PATH.exists():
        return True

    subprocess.run(
        ["launchctl", "unload", str(LAUNCHD_PLIST_PATH)], capture_output=True
    )
    LAUNCHD_PLIST_PATH.unlink(missing_ok=True)
    return True


def _get_launchd_status() -> Optional[dict]:
    """Check if launchd job is installed."""
    if not LAUNCHD_PLIST_PATH.exists():
        return None

    # Check if loaded
    result = subprocess.run(
        ["launchctl", "list", "com.freckle.save"],
        capture_output=True,
        text=True,
    )

    is_loaded = result.returncode == 0

    # Parse plist for schedule info
    import plistlib

    try:
        with open(LAUNCHD_PLIST_PATH, "rb") as f:
            plist = plistlib.load(f)
        interval = plist.get("StartCalendarInterval", {})
        hour = interval.get("Hour", 9)
        minute = interval.get("Minute", 0)
        weekday = interval.get("Weekday")

        if weekday is not None:
            schedule = f"Weekly (Sunday) at {hour:02d}:{minute:02d}"
        else:
            schedule = f"Daily at {hour:02d}:{minute:02d}"

        return {
            "installed": True,
            "loaded": is_loaded,
            "schedule": schedule,
            "path": str(LAUNCHD_PLIST_PATH),
        }
    except Exception:
        return {"installed": True, "loaded": is_loaded, "schedule": "Unknown"}


def _install_cron(hour: int, minute: int, daily: bool = True) -> bool:
    """Install cron job for Linux scheduled saves."""
    freckle_path = _get_freckle_path()

    if daily:
        cron_schedule = f"{minute} {hour} * * *"
    else:
        cron_schedule = f"{minute} {hour} * * 0"  # Sunday

    cron_line = (
        f"{cron_schedule} {freckle_path} save "
        f"--quiet --scheduled {CRON_MARKER}"
    )

    # Get existing crontab
    result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    existing = result.stdout if result.returncode == 0 else ""

    # Remove any existing freckle lines
    lines = [line for line in existing.splitlines() if CRON_MARKER not in line]
    lines.append(cron_line)

    new_crontab = "\n".join(lines) + "\n"

    # Install new crontab
    result = subprocess.run(
        ["crontab", "-"], input=new_crontab, capture_output=True, text=True
    )

    return result.returncode == 0


def _uninstall_cron() -> bool:
    """Remove cron job."""
    result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    if result.returncode != 0:
        return True

    lines = [
        line for line in result.stdout.splitlines() if CRON_MARKER not in line
    ]
    new_crontab = "\n".join(lines) + "\n" if lines else ""

    if new_crontab.strip():
        subprocess.run(
            ["crontab", "-"], input=new_crontab, capture_output=True, text=True
        )
    else:
        subprocess.run(["crontab", "-r"], capture_output=True)

    return True


def _get_cron_status() -> Optional[dict]:
    """Check if cron job is installed."""
    result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    if result.returncode != 0:
        return None

    for line in result.stdout.splitlines():
        if CRON_MARKER in line:
            # Parse schedule from cron line
            parts = line.split()
            if len(parts) >= 5:
                minute, hour, dom, month, dow = parts[:5]
                if dow == "0":
                    schedule = f"Weekly (Sunday) at {hour}:{minute.zfill(2)}"
                else:
                    schedule = f"Daily at {hour}:{minute.zfill(2)}"
                return {
                    "installed": True,
                    "schedule": schedule,
                    "cron_line": line,
                }

    return None


def schedule(
    frequency: Optional[str] = typer.Argument(
        None, help="Frequency: 'daily', 'weekly', or 'off' to disable"
    ),
    hour: int = typer.Option(9, "--hour", "-H", help="Hour to run (0-23)"),
    minute: int = typer.Option(
        0, "--minute", "-M", help="Minute to run (0-59)"
    ),
):
    """Set up automatic scheduled saves.

    Examples:
        freckle schedule daily          # Save daily at 9:00 AM
        freckle schedule weekly         # Save weekly (Sunday) at 9:00 AM
        freckle schedule daily -H 14    # Save daily at 2:00 PM
        freckle schedule off            # Disable scheduled saves
        freckle schedule                # Show current schedule status

    On macOS, uses launchd (~/Library/LaunchAgents/).
    On Linux, uses cron.
    """

    is_mac = env.os_info.get("system") == "Darwin"

    if frequency is None:
        # Show status
        if is_mac:
            status = _get_launchd_status()
        else:
            status = _get_cron_status()

        if status:
            header("--- Scheduled Save Status ---")
            plain("  Enabled : Yes")
            plain(f"  Schedule: {status['schedule']}")
            if is_mac and "loaded" in status:
                plain(f"  Loaded  : {'Yes' if status['loaded'] else 'No'}")
            if "path" in status:
                muted(f"  Path    : {status['path']}")
            muted("\nLog file: /tmp/freckle-save.log")
        else:
            plain("\nNo scheduled save configured.")
            muted(
                "Run 'freckle schedule daily' or "
                "'freckle schedule weekly' to enable."
            )
        return

    if frequency.lower() == "off":
        # Disable
        if is_mac:
            result = _uninstall_launchd()
        else:
            result = _uninstall_cron()

        if result:
            success("Scheduled saves disabled.")
        else:
            error("Failed to disable scheduled saves.")
            raise typer.Exit(1)
        return

    if frequency.lower() not in ["daily", "weekly"]:
        error(
            f"Invalid frequency: {frequency}. "
            "Use 'daily', 'weekly', or 'off'."
        )
        raise typer.Exit(1)

    daily = frequency.lower() == "daily"

    if is_mac:
        result = _install_launchd(hour, minute, daily)
    else:
        result = _install_cron(hour, minute, daily)

    if result:
        schedule_desc = "daily" if daily else "weekly (Sunday)"
        success(f"Scheduled {schedule_desc} save at {hour:02d}:{minute:02d}")
        muted("  Log file: /tmp/freckle-save.log")
        if is_mac:
            muted(f"  Config  : {LAUNCHD_PLIST_PATH}")
    else:
        error("Failed to set up scheduled save.")
        raise typer.Exit(1)
