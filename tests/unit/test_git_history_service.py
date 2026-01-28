"""Tests for GitHistoryService."""

from unittest.mock import MagicMock, patch

from freckle.dotfiles.history import CommitInfo, GitHistoryService


class TestGitHistoryService:
    """Tests for GitHistoryService."""

    def test_init(self, tmp_path):
        """Service initializes with git_dir and work_tree."""
        git_dir = tmp_path / ".dotfiles"
        work_tree = tmp_path / "home"

        service = GitHistoryService(git_dir, work_tree)

        assert service.git_dir == git_dir
        assert service.work_tree == work_tree

    def test_is_valid_commit_success(self, tmp_path):
        """Returns True for valid commit."""
        service = GitHistoryService(tmp_path, tmp_path)

        with patch.object(service, "_run_git") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            result = service.is_valid_commit("abc123")

            assert result is True
            mock_run.assert_called_once()

    def test_is_valid_commit_failure(self, tmp_path):
        """Returns False for invalid commit."""
        service = GitHistoryService(tmp_path, tmp_path)

        with patch.object(service, "_run_git") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)

            result = service.is_valid_commit("invalid")

            assert result is False

    def test_get_commit_subject(self, tmp_path):
        """Returns commit subject line."""
        service = GitHistoryService(tmp_path, tmp_path)

        with patch.object(service, "_run_git") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="Fix bug in config\n",
            )

            result = service.get_commit_subject("abc123")

            assert result == "Fix bug in config"

    def test_get_commit_subject_not_found(self, tmp_path):
        """Returns None when commit not found."""
        service = GitHistoryService(tmp_path, tmp_path)

        with patch.object(service, "_run_git") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)

            result = service.get_commit_subject("invalid")

            assert result is None

    def test_get_file_at_commit(self, tmp_path):
        """Returns file contents at commit."""
        service = GitHistoryService(tmp_path, tmp_path)

        with patch.object(service, "_run_git") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="file contents here",
            )

            result = service.get_file_at_commit("abc123", ".zshrc")

            assert result == "file contents here"

    def test_get_file_at_commit_not_found(self, tmp_path):
        """Returns None when file not in commit."""
        service = GitHistoryService(tmp_path, tmp_path)

        with patch.object(service, "_run_git") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)

            result = service.get_file_at_commit("abc123", "nonexistent")

            assert result is None

    def test_get_commit_files(self, tmp_path):
        """Returns list of files changed in commit."""
        service = GitHistoryService(tmp_path, tmp_path)

        with patch.object(service, "_run_git") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=".zshrc\n.gitconfig\n.tmux.conf\n",
            )

            result = service.get_commit_files("abc123")

            assert result == [".zshrc", ".gitconfig", ".tmux.conf"]

    def test_get_commit_files_with_filter(self, tmp_path):
        """Filters files by path prefix."""
        service = GitHistoryService(tmp_path, tmp_path)

        with patch.object(service, "_run_git") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=".config/nvim/init.lua\n.zshrc\n.config/nvim/lua/x.lua\n",
            )

            result = service.get_commit_files(
                "abc123", filter_paths=[".config/nvim"]
            )

            assert result == [
                ".config/nvim/init.lua",
                ".config/nvim/lua/x.lua",
            ]

    def test_get_diff(self, tmp_path):
        """Returns diff between two commits."""
        service = GitHistoryService(tmp_path, tmp_path)

        with patch.object(service, "_run_git") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="diff --git a/.zshrc b/.zshrc\n...",
            )

            result = service.get_diff("abc123", "def456")

            assert "diff --git" in result


class TestCommitInfo:
    """Tests for CommitInfo dataclass."""

    def test_commit_info_creation(self):
        """CommitInfo can be created with all fields."""
        commit = CommitInfo(
            hash="abc123f",
            date="2 hours ago",
            date_raw="2024-01-15T10:30:00+00:00",
            author="Test User",
            subject="Update config",
            files=[".zshrc", ".gitconfig"],
        )

        assert commit.hash == "abc123f"
        assert commit.date == "2 hours ago"
        assert commit.author == "Test User"
        assert commit.subject == "Update config"
        assert len(commit.files) == 2
