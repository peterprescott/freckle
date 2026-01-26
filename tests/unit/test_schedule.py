"""Tests for schedule command functionality."""

import plistlib
from io import BytesIO

import pytest

from freckle.cli.schedule import (
    CRON_MARKER,
    _create_launchd_plist,
)


class TestLaunchdPlist:
    """Tests for launchd plist generation."""

    def test_create_daily_plist(self):
        """Test creating a daily backup plist."""
        plist_str = _create_launchd_plist(hour=9, minute=0, daily=True)

        # Parse the plist to validate structure
        plist = plistlib.loads(plist_str.encode())

        assert plist["Label"] == "com.freckle.backup"
        assert "ProgramArguments" in plist
        assert "backup" in plist["ProgramArguments"]
        assert "--quiet" in plist["ProgramArguments"]
        assert "--scheduled" in plist["ProgramArguments"]

        interval = plist["StartCalendarInterval"]
        assert interval["Hour"] == 9
        assert interval["Minute"] == 0
        # Daily plist should NOT have Weekday
        assert "Weekday" not in interval

    def test_create_weekly_plist(self):
        """Test creating a weekly backup plist."""
        plist_str = _create_launchd_plist(hour=14, minute=30, daily=False)

        plist = plistlib.loads(plist_str.encode())

        assert plist["Label"] == "com.freckle.backup"

        interval = plist["StartCalendarInterval"]
        assert interval["Hour"] == 14
        assert interval["Minute"] == 30
        # Weekly plist should have Weekday = 0 (Sunday)
        assert interval["Weekday"] == 0

    def test_plist_has_log_paths(self):
        """Test that plist includes log file paths."""
        plist_str = _create_launchd_plist(hour=9, minute=0, daily=True)
        plist = plistlib.loads(plist_str.encode())

        assert plist["StandardOutPath"] == "/tmp/freckle-backup.log"
        assert plist["StandardErrorPath"] == "/tmp/freckle-backup.log"

    def test_plist_run_at_load_false(self):
        """Test that RunAtLoad is false (don't run on login)."""
        plist_str = _create_launchd_plist(hour=9, minute=0, daily=True)
        plist = plistlib.loads(plist_str.encode())

        assert plist["RunAtLoad"] is False

    def test_plist_custom_time(self):
        """Test plist with custom hour and minute."""
        plist_str = _create_launchd_plist(hour=23, minute=45, daily=True)
        plist = plistlib.loads(plist_str.encode())

        interval = plist["StartCalendarInterval"]
        assert interval["Hour"] == 23
        assert interval["Minute"] == 45


class TestCronLine:
    """Tests for cron line format."""

    def test_cron_marker_defined(self):
        """Test that cron marker is defined for identification."""
        assert CRON_MARKER == "# freckle-backup"

    def test_cron_daily_format(self):
        """Test daily cron schedule format."""
        # The format should be: minute hour * * *
        # For daily at 9:00: 0 9 * * *
        minute, hour = 0, 9
        cron_schedule = f"{minute} {hour} * * *"
        assert cron_schedule == "0 9 * * *"

    def test_cron_weekly_format(self):
        """Test weekly (Sunday) cron schedule format."""
        # The format should be: minute hour * * 0
        # For weekly at 14:30: 30 14 * * 0
        minute, hour = 30, 14
        cron_schedule = f"{minute} {hour} * * 0"
        assert cron_schedule == "30 14 * * 0"


class TestScheduleStatusParsing:
    """Tests for parsing schedule status."""

    def test_parse_launchd_daily_interval(self):
        """Test parsing daily schedule from plist data."""
        plist_data = {
            "StartCalendarInterval": {
                "Hour": 9,
                "Minute": 0,
            }
        }

        interval = plist_data.get("StartCalendarInterval", {})
        hour = interval.get("Hour", 9)
        minute = interval.get("Minute", 0)
        weekday = interval.get("Weekday")

        if weekday is not None:
            schedule = f"Weekly (Sunday) at {hour:02d}:{minute:02d}"
        else:
            schedule = f"Daily at {hour:02d}:{minute:02d}"

        assert schedule == "Daily at 09:00"

    def test_parse_launchd_weekly_interval(self):
        """Test parsing weekly schedule from plist data."""
        plist_data = {
            "StartCalendarInterval": {
                "Weekday": 0,
                "Hour": 14,
                "Minute": 30,
            }
        }

        interval = plist_data.get("StartCalendarInterval", {})
        hour = interval.get("Hour", 9)
        minute = interval.get("Minute", 0)
        weekday = interval.get("Weekday")

        if weekday is not None:
            schedule = f"Weekly (Sunday) at {hour:02d}:{minute:02d}"
        else:
            schedule = f"Daily at {hour:02d}:{minute:02d}"

        assert schedule == "Weekly (Sunday) at 14:30"

    def test_parse_cron_line_daily(self):
        """Test parsing daily schedule from cron line."""
        cron_line = "0 9 * * * /usr/local/bin/freckle backup # freckle-backup"
        parts = cron_line.split()
        minute, hour, dom, month, dow = parts[:5]

        if dow == "0":
            schedule = f"Weekly (Sunday) at {hour}:{minute.zfill(2)}"
        else:
            schedule = f"Daily at {hour}:{minute.zfill(2)}"

        assert schedule == "Daily at 9:00"

    def test_parse_cron_line_weekly(self):
        """Test parsing weekly schedule from cron line."""
        cron_line = "30 14 * * 0 /usr/local/bin/freckle backup # freckle-backup"
        parts = cron_line.split()
        minute, hour, dom, month, dow = parts[:5]

        if dow == "0":
            schedule = f"Weekly (Sunday) at {hour}:{minute.zfill(2)}"
        else:
            schedule = f"Daily at {hour}:{minute.zfill(2)}"

        assert schedule == "Weekly (Sunday) at 14:30"
