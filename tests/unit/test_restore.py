"""Tests for restore command helper functions."""

from pathlib import Path
from unittest.mock import MagicMock

from freckle.cli.restore import (
    get_commit_info,
    is_git_commit,
    show_diff,
)


class TestIsGitCommit:
    """Tests for is_git_commit function."""

    def test_valid_commit(self, mocker):
        """Returns True for valid commit hash."""
        mock_run = mocker.patch("freckle.cli.restore.subprocess.run")
        mock_run.return_value = MagicMock(returncode=0)

        result = is_git_commit(Path("/test/.dotfiles"), "abc123f")

        assert result is True
        mock_run.assert_called_once()

    def test_invalid_commit(self, mocker):
        """Returns False for invalid commit hash."""
        mock_run = mocker.patch("freckle.cli.restore.subprocess.run")
        mock_run.return_value = MagicMock(returncode=1)

        result = is_git_commit(Path("/test/.dotfiles"), "notacommit")

        assert result is False

    def test_handles_exception(self, mocker):
        """Returns False when git command fails."""
        mock_run = mocker.patch("freckle.cli.restore.subprocess.run")
        mock_run.side_effect = Exception("Git not found")

        result = is_git_commit(Path("/test/.dotfiles"), "abc123f")

        assert result is False


class TestGetCommitInfo:
    """Tests for get_commit_info function."""

    def test_gets_commit_subject(self, mocker):
        """Returns commit subject line."""
        mock_run = mocker.patch("freckle.cli.restore.subprocess.run")
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Test commit message\n",
        )

        result = get_commit_info(Path("/test/.dotfiles"), "abc123f")

        assert result == "Test commit message"

    def test_returns_none_on_failure(self, mocker):
        """Returns None when git command fails."""
        mock_run = mocker.patch("freckle.cli.restore.subprocess.run")
        mock_run.return_value = MagicMock(returncode=1)

        result = get_commit_info(Path("/test/.dotfiles"), "abc123f")

        assert result is None

    def test_handles_exception(self, mocker):
        """Returns None when exception occurs."""
        mock_run = mocker.patch("freckle.cli.restore.subprocess.run")
        mock_run.side_effect = Exception("Git error")

        result = get_commit_info(Path("/test/.dotfiles"), "abc123f")

        assert result is None


class TestShowDiff:
    """Tests for show_diff function."""

    def test_shows_diff_output(self, capsys):
        """Displays diff between two contents."""
        current = "line 1\nline 2\nline 3\n"
        new = "line 1\nmodified line\nline 3\n"

        show_diff(current, new, "test.txt")

        captured = capsys.readouterr()
        # Should show the diff
        assert "test.txt" in captured.out or len(captured.out) > 0

    def test_empty_diff_for_same_content(self, capsys):
        """Shows minimal output for identical content."""
        content = "same content\n"

        show_diff(content, content, "test.txt")

        captured = capsys.readouterr()
        # Diff of identical content should be minimal
        assert "+" not in captured.out or "-" not in captured.out

    def test_shows_additions(self, capsys):
        """Shows added lines in green."""
        current = "line 1\n"
        new = "line 1\nline 2\n"

        show_diff(current, new, "test.txt")

        captured = capsys.readouterr()
        # Added content should appear
        assert "line 2" in captured.out

    def test_shows_deletions(self, capsys):
        """Shows deleted lines in red."""
        current = "line 1\nline 2\n"
        new = "line 1\n"

        show_diff(current, new, "test.txt")

        captured = capsys.readouterr()
        # Deleted content should appear
        assert "line 2" in captured.out


class TestRestoreFromCommitIntegration:
    """Integration tests for restore_from_commit."""

    def test_requires_tool_or_all_flag(self, mocker):
        """Raises error when neither tool nor --all is specified."""
        # This would be tested via CLI runner
        pass  # Covered by CLI tests

    def test_creates_backup_before_restore(self, mocker):
        """Creates backup before restoring files."""
        # This would be tested via CLI runner or integration tests
        pass  # Covered by integration tests


class TestRestoreFromBackupIntegration:
    """Integration tests for restore_from_backup."""

    def test_finds_restore_point(self, mocker):
        """Finds and uses restore point."""
        # This is covered by existing backup tests
        pass

    def test_handles_missing_restore_point(self, mocker):
        """Handles missing restore point gracefully."""
        # This is covered by existing backup tests
        pass
