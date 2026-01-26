"""Tests for dotfiles operations."""

from unittest.mock import MagicMock

import pytest

from freckle.dotfiles.operations import (
    add_files,
    commit_and_push,
    force_checkout,
    push,
)


class TestAddFiles:
    """Tests for add_files function."""

    def test_repo_not_initialized_returns_error(self, tmp_path):
        """Returns error when repo doesn't exist."""
        mock_git = MagicMock()
        mock_git.git_dir = tmp_path / "nonexistent"

        result = add_files(mock_git, tmp_path, [".zshrc"])

        assert result["success"] is False
        assert "not initialized" in result["error"].lower()
        assert result["added"] == []

    def test_file_not_found_is_skipped(self, tmp_path):
        """Non-existent files are skipped."""
        git_dir = tmp_path / ".dotfiles"
        git_dir.mkdir()

        mock_git = MagicMock()
        mock_git.git_dir = git_dir

        result = add_files(mock_git, tmp_path, ["nonexistent.txt"])

        assert result["success"] is True  # No files to add is still success
        assert result["added"] == []
        assert "nonexistent.txt" in result["skipped"]

    def test_successful_add(self, tmp_path):
        """Successfully adds existing files."""
        git_dir = tmp_path / ".dotfiles"
        git_dir.mkdir()

        # Create test file
        test_file = tmp_path / ".zshrc"
        test_file.write_text("# zshrc")

        mock_git = MagicMock()
        mock_git.git_dir = git_dir
        mock_git.run.return_value = MagicMock(returncode=0)

        result = add_files(mock_git, tmp_path, [".zshrc"])

        assert result["success"] is True
        assert ".zshrc" in result["added"]
        assert result["skipped"] == []

    def test_git_add_failure_skips_file(self, tmp_path):
        """Files that fail to add are skipped."""
        git_dir = tmp_path / ".dotfiles"
        git_dir.mkdir()

        test_file = tmp_path / ".zshrc"
        test_file.write_text("# zshrc")

        mock_git = MagicMock()
        mock_git.git_dir = git_dir
        mock_git.run.return_value = MagicMock(returncode=1, stderr="error")

        result = add_files(mock_git, tmp_path, [".zshrc"])

        assert ".zshrc" in result["skipped"]
        assert result["added"] == []

    def test_exception_during_add_skips_file(self, tmp_path):
        """Exception during add skips the file."""
        git_dir = tmp_path / ".dotfiles"
        git_dir.mkdir()

        test_file = tmp_path / ".zshrc"
        test_file.write_text("# zshrc")

        mock_git = MagicMock()
        mock_git.git_dir = git_dir
        mock_git.run.side_effect = Exception("Git error")

        result = add_files(mock_git, tmp_path, [".zshrc"])

        assert ".zshrc" in result["skipped"]


class TestCommitAndPush:
    """Tests for commit_and_push function."""

    def test_no_changes_returns_success(self):
        """No changes to commit returns success with message."""
        mock_git = MagicMock()
        get_changed = MagicMock(return_value=[])

        result = commit_and_push(mock_git, "main", "Test commit", get_changed)

        assert result["success"] is True
        assert "no changes" in result["error"].lower()
        assert result["committed"] is False

    def test_git_add_failure(self):
        """Git add failure returns error."""
        mock_git = MagicMock()
        mock_git.run.return_value = MagicMock(
            returncode=1, stderr="add failed"
        )
        get_changed = MagicMock(return_value=[".zshrc"])

        result = commit_and_push(mock_git, "main", "Test commit", get_changed)

        assert result["success"] is False
        assert "add failed" in result["error"]

    def test_nothing_to_commit_message(self):
        """'Nothing to commit' is handled gracefully."""
        mock_git = MagicMock()
        mock_git.run.side_effect = [
            MagicMock(returncode=0),  # git add
            MagicMock(
                returncode=1,
                stdout="nothing to commit",
                stderr=""
            ),  # git commit
        ]
        get_changed = MagicMock(return_value=[".zshrc"])

        result = commit_and_push(mock_git, "main", "Test commit", get_changed)

        assert result["success"] is True
        assert "no changes" in result["error"].lower()

    def test_commit_failure(self):
        """Commit failure returns error."""
        mock_git = MagicMock()
        mock_git.run.side_effect = [
            MagicMock(returncode=0),  # git add
            MagicMock(
                returncode=1,
                stdout="",
                stderr="commit failed"
            ),  # git commit
        ]
        get_changed = MagicMock(return_value=[".zshrc"])

        result = commit_and_push(mock_git, "main", "Test commit", get_changed)

        assert result["success"] is False
        assert "commit failed" in result["error"]

    def test_successful_commit_and_push(self):
        """Successful commit and push."""
        mock_git = MagicMock()
        mock_git.run.side_effect = [
            MagicMock(returncode=0),  # git add
            MagicMock(returncode=0, stdout="", stderr=""),  # git commit
        ]
        mock_git.run_bare.return_value = MagicMock(returncode=0)
        get_changed = MagicMock(return_value=[".zshrc"])

        result = commit_and_push(mock_git, "main", "Test commit", get_changed)

        assert result["success"] is True
        assert result["committed"] is True
        assert result["pushed"] is True

    def test_push_failure_after_commit(self):
        """Push failure after successful commit."""
        mock_git = MagicMock()
        mock_git.run.side_effect = [
            MagicMock(returncode=0),  # git add
            MagicMock(returncode=0, stdout="", stderr=""),  # git commit
        ]
        mock_git.run_bare.return_value = MagicMock(
            returncode=1, stderr="push rejected"
        )
        get_changed = MagicMock(return_value=[".zshrc"])

        result = commit_and_push(mock_git, "main", "Test commit", get_changed)

        assert result["success"] is False
        assert result["committed"] is True
        assert result["pushed"] is False
        assert "push" in result["error"].lower()


class TestPush:
    """Tests for push function."""

    def test_successful_push(self):
        """Successful push returns success."""
        mock_git = MagicMock()
        mock_git.run_bare.return_value = MagicMock(returncode=0)

        result = push(mock_git, "main")

        assert result["success"] is True
        assert result["error"] is None

    def test_push_failure(self):
        """Push failure returns error."""
        mock_git = MagicMock()
        mock_git.run_bare.return_value = MagicMock(
            returncode=1, stderr="remote rejected"
        )

        result = push(mock_git, "main")

        assert result["success"] is False
        assert "remote rejected" in result["error"]

    def test_push_exception(self):
        """Exception during push returns error."""
        mock_git = MagicMock()
        mock_git.run_bare.side_effect = Exception("Network error")

        result = push(mock_git, "main")

        assert result["success"] is False
        assert "Network error" in result["error"]


class TestForceCheckout:
    """Tests for force_checkout function."""

    def test_successful_reset(self):
        """Successful force checkout."""
        mock_git = MagicMock()
        mock_git.fetch.return_value = True
        mock_git.run.return_value = MagicMock(returncode=0)

        # Should not raise
        force_checkout(mock_git, "main")

        mock_git.fetch.assert_called_once()
        mock_git.run.assert_called_once_with(
            "reset", "--hard", "origin/main"
        )

    def test_reset_failure_raises(self):
        """Reset failure raises RuntimeError."""
        mock_git = MagicMock()
        mock_git.fetch.return_value = True
        mock_git.run.side_effect = Exception("Reset failed")

        with pytest.raises(RuntimeError, match="Reset failed"):
            force_checkout(mock_git, "main")


class TestCommitAndPushExceptionHandling:
    """Tests for commit_and_push exception handling."""

    def test_commit_exception_returns_error(self):
        """Exception during commit returns error."""
        mock_git = MagicMock()
        mock_git.run.side_effect = [
            MagicMock(returncode=0),  # git add succeeds
            Exception("Commit failed unexpectedly"),  # git commit fails
        ]
        get_changed = MagicMock(return_value=[".zshrc"])

        result = commit_and_push(mock_git, "main", "Test commit", get_changed)

        assert result["success"] is False
        assert "Commit failed" in result["error"]

    def test_push_exception_returns_error(self):
        """Exception during push returns error."""
        mock_git = MagicMock()
        mock_git.run.side_effect = [
            MagicMock(returncode=0),  # git add
            MagicMock(returncode=0, stdout="", stderr=""),  # git commit
        ]
        mock_git.run_bare.side_effect = Exception("Network error")
        get_changed = MagicMock(return_value=[".zshrc"])

        result = commit_and_push(mock_git, "main", "Test commit", get_changed)

        assert result["success"] is False
        assert result["committed"] is True
        assert "Push failed" in result["error"]
