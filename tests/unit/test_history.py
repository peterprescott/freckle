"""Tests for history command helper functions."""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

from freckle.cli.history import (
    display_commit,
    format_relative_date,
    resolve_to_repo_paths,
)


class TestFormatRelativeDate:
    """Tests for format_relative_date function."""

    def test_just_now(self):
        """Returns 'just now' for very recent times."""
        now = datetime.now(timezone.utc)
        result = format_relative_date(now)
        assert result == "just now"

    def test_minutes_ago(self):
        """Returns minutes ago for recent times."""
        from datetime import timedelta

        past = datetime.now(timezone.utc) - timedelta(minutes=5)
        result = format_relative_date(past)
        assert "minute" in result
        assert "5" in result

    def test_hours_ago(self):
        """Returns hours ago for same-day times."""
        from datetime import timedelta

        past = datetime.now(timezone.utc) - timedelta(hours=3)
        result = format_relative_date(past)
        assert "hour" in result
        assert "3" in result

    def test_yesterday(self):
        """Returns 'yesterday' for previous day."""
        from datetime import timedelta

        past = datetime.now(timezone.utc) - timedelta(days=1)
        result = format_relative_date(past)
        assert result == "yesterday"

    def test_days_ago(self):
        """Returns days ago for recent past."""
        from datetime import timedelta

        past = datetime.now(timezone.utc) - timedelta(days=4)
        result = format_relative_date(past)
        assert "day" in result
        assert "4" in result

    def test_weeks_ago(self):
        """Returns weeks ago for medium past."""
        from datetime import timedelta

        past = datetime.now(timezone.utc) - timedelta(weeks=2)
        result = format_relative_date(past)
        assert "week" in result
        assert "2" in result

    def test_months_ago(self):
        """Returns months ago for longer past."""
        from datetime import timedelta

        past = datetime.now(timezone.utc) - timedelta(days=60)
        result = format_relative_date(past)
        assert "month" in result
        assert "2" in result

    def test_old_date(self):
        """Returns date format for very old dates."""
        from datetime import timedelta

        past = datetime.now(timezone.utc) - timedelta(days=400)
        result = format_relative_date(past)
        assert "-" in result  # ISO-ish format


class TestResolveToRepoPaths:
    """Tests for resolve_to_repo_paths function."""

    def test_tilde_path(self, mocker):
        """Expands ~ paths to repo-relative."""
        mock_config = MagicMock()
        mock_config.data = {"tools": {}}

        # Use actual home since Path.expanduser() uses OS home
        actual_home = Path.home()
        mocker.patch(
            "freckle.cli.history.env",
            MagicMock(home=actual_home),
        )

        result = resolve_to_repo_paths(
            "~/.zshrc",
            mock_config,
            actual_home / ".dotfiles",
        )

        assert result == [".zshrc"]

    def test_absolute_path(self, mocker):
        """Converts absolute paths under home to relative."""
        mock_config = MagicMock()
        mock_config.data = {"tools": {}}

        mocker.patch(
            "freckle.cli.history.env",
            MagicMock(home=Path("/Users/test")),
        )

        result = resolve_to_repo_paths(
            "/Users/test/.config/nvim/init.lua",
            mock_config,
            Path("/Users/test/.dotfiles"),
        )

        assert result == [".config/nvim/init.lua"]

    def test_relative_dotfile_path(self, mocker):
        """Handles paths starting with dot."""
        mock_config = MagicMock()
        mock_config.data = {"tools": {}}

        mocker.patch(
            "freckle.cli.history.env",
            MagicMock(home=Path("/Users/test")),
        )

        result = resolve_to_repo_paths(
            ".zshrc",
            mock_config,
            Path("/Users/test/.dotfiles"),
        )

        assert result == [".zshrc"]

    def test_tool_with_single_config(self, mocker):
        """Resolves tool with single config file."""
        mock_config = MagicMock()
        mock_config.data = {
            "tools": {
                "zsh": {
                    "config": [".zshrc"],
                }
            }
        }

        mocker.patch(
            "freckle.cli.history.env",
            MagicMock(home=Path("/Users/test")),
        )

        result = resolve_to_repo_paths(
            "zsh",
            mock_config,
            Path("/Users/test/.dotfiles"),
        )

        assert result == [".zshrc"]

    def test_tool_with_multiple_configs(self, mocker):
        """Resolves tool with multiple config files."""
        mock_config = MagicMock()
        mock_config.data = {
            "tools": {
                "zsh": {
                    "config": [".zshrc", ".zshenv", ".zprofile"],
                }
            }
        }

        mocker.patch(
            "freckle.cli.history.env",
            MagicMock(home=Path("/Users/test")),
        )

        result = resolve_to_repo_paths(
            "zsh",
            mock_config,
            Path("/Users/test/.dotfiles"),
        )

        assert result == [".zshrc", ".zshenv", ".zprofile"]

    def test_tool_with_no_config_defined(self, mocker):
        """Returns empty list for tool with no config defined."""
        mock_config = MagicMock()
        mock_config.data = {
            "tools": {
                "nvim": {
                    "description": "Neovim",
                    # No config key
                }
            }
        }

        mocker.patch(
            "freckle.cli.history.env",
            MagicMock(home=Path("/Users/test")),
        )

        result = resolve_to_repo_paths(
            "nvim",
            mock_config,
            Path("/Users/test/.dotfiles"),
        )

        assert result == []

    def test_unknown_tool_returns_empty(self, mocker):
        """Returns empty list for unknown tools."""
        mock_config = MagicMock()
        mock_config.data = {"tools": {}}

        mocker.patch(
            "freckle.cli.history.env",
            MagicMock(home=Path("/Users/test")),
        )

        result = resolve_to_repo_paths(
            "unknowntool",
            mock_config,
            Path("/Users/test/.dotfiles"),
        )

        assert result == []


class TestDisplayCommit:
    """Tests for display_commit function."""

    def test_display_basic_commit(self, capsys):
        """Displays basic commit information."""
        commit = {
            "hash": "abc123f",
            "date": "2 hours ago",
            "author": "Test User",
            "subject": "Test commit message",
            "files": [],
        }

        display_commit(commit, show_files=False)

        captured = capsys.readouterr()
        assert "abc123f" in captured.out
        assert "2 hours ago" in captured.out
        assert "Test User" in captured.out
        assert "Test commit message" in captured.out

    def test_display_commit_with_files(self, capsys):
        """Displays commit with file list."""
        commit = {
            "hash": "abc123f",
            "date": "2 hours ago",
            "author": "Test User",
            "subject": "Test commit message",
            "files": [".zshrc", ".config/nvim/init.lua"],
        }

        display_commit(commit, show_files=True)

        captured = capsys.readouterr()
        assert "2 file(s) changed" in captured.out
        assert ".zshrc" in captured.out
        assert ".config/nvim/init.lua" in captured.out


class TestIsValidCommit:
    """Tests for is_valid_commit function."""

    def test_valid_commit(self, mocker):
        """Returns True for valid commit."""
        from freckle.cli.history import is_valid_commit

        mock_run = mocker.patch("freckle.cli.history.subprocess.run")
        mock_run.return_value = MagicMock(returncode=0)

        result = is_valid_commit(Path("/test/.dotfiles"), "abc123")
        assert result is True

    def test_invalid_commit(self, mocker):
        """Returns False for invalid commit."""
        from freckle.cli.history import is_valid_commit

        mock_run = mocker.patch("freckle.cli.history.subprocess.run")
        mock_run.return_value = MagicMock(returncode=1)

        result = is_valid_commit(Path("/test/.dotfiles"), "invalid")
        assert result is False


class TestDisplayColoredDiff:
    """Tests for display_colored_diff function."""

    def test_displays_additions_in_green(self, capsys):
        """Additions are displayed."""
        from freckle.cli.history import display_colored_diff

        diff = "+added line\n context\n-removed line"
        display_colored_diff(diff)

        captured = capsys.readouterr()
        assert "added line" in captured.out
        assert "removed line" in captured.out

    def test_skips_git_headers(self, capsys):
        """Git headers are skipped."""
        from freckle.cli.history import display_colored_diff

        diff = "diff --git a/file b/file\nindex 123..456\n+added"
        display_colored_diff(diff)

        captured = capsys.readouterr()
        assert "diff --git" not in captured.out
        assert "index " not in captured.out
        assert "added" in captured.out
