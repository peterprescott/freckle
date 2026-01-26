"""Tests for BareGitRepo class."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from freckle.dotfiles.repo import BareGitRepo


class TestBareGitRepo:
    """Tests for BareGitRepo initialization and basic methods."""

    def test_init_sets_paths(self, tmp_path):
        """Initializes with correct paths."""
        git_dir = tmp_path / ".dotfiles"
        work_tree = tmp_path / "home"
        repo = BareGitRepo(git_dir, work_tree)

        assert repo.git_dir == git_dir
        assert repo.work_tree == work_tree


class TestCloneBare:
    """Tests for clone_bare method."""

    def test_clone_success(self, tmp_path):
        """Successful clone."""
        git_dir = tmp_path / ".dotfiles"
        repo = BareGitRepo(git_dir, tmp_path)

        with patch("freckle.dotfiles.repo.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            repo.clone_bare("https://github.com/user/repo.git")

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "clone" in args
        assert "--bare" in args

    def test_clone_failure_raises(self, tmp_path):
        """Clone failure raises CalledProcessError."""
        git_dir = tmp_path / ".dotfiles"
        repo = BareGitRepo(git_dir, tmp_path)

        with patch("freckle.dotfiles.repo.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(
                1, "git", stderr="fatal: repository not found"
            )
            with pytest.raises(subprocess.CalledProcessError):
                repo.clone_bare("https://github.com/user/nonexistent.git")


class TestInitBare:
    """Tests for init_bare method."""

    def test_init_bare_success(self, tmp_path):
        """Successfully initializes bare repo."""
        git_dir = tmp_path / ".dotfiles"
        repo = BareGitRepo(git_dir, tmp_path)

        with patch("freckle.dotfiles.repo.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            repo.init_bare(initial_branch="main")

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "init" in args
        assert "--bare" in args
        assert "--initial-branch=main" in args


class TestEnsureFetchRefspec:
    """Tests for ensure_fetch_refspec method."""

    def test_ensure_fetch_refspec_exception(self, tmp_path):
        """Handles exceptions gracefully."""
        repo = BareGitRepo(tmp_path / ".dotfiles", tmp_path)

        with patch.object(repo, "run_bare") as mock_run:
            mock_run.side_effect = Exception("Config error")
            # Should not raise
            repo.ensure_fetch_refspec()


class TestFetch:
    """Tests for fetch method."""

    def test_fetch_success(self, tmp_path):
        """Successful fetch returns True."""
        repo = BareGitRepo(tmp_path / ".dotfiles", tmp_path)

        with patch.object(repo, "run_bare") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = repo.fetch()

        assert result is True

    def test_fetch_timeout_returns_false(self, tmp_path):
        """Fetch timeout returns False."""
        repo = BareGitRepo(tmp_path / ".dotfiles", tmp_path)

        with patch.object(repo, "ensure_fetch_refspec"):
            with patch.object(repo, "run_bare") as mock_run:
                mock_run.side_effect = subprocess.TimeoutExpired(
                    cmd="git", timeout=60
                )
                result = repo.fetch()

        assert result is False

    def test_fetch_called_process_error_returns_false(self, tmp_path):
        """Fetch CalledProcessError returns False."""
        repo = BareGitRepo(tmp_path / ".dotfiles", tmp_path)

        with patch.object(repo, "ensure_fetch_refspec"):
            with patch.object(repo, "run_bare") as mock_run:
                mock_run.side_effect = subprocess.CalledProcessError(
                    1, "git", stderr="network unreachable"
                )
                result = repo.fetch()

        assert result is False

    def test_fetch_generic_exception_returns_false(self, tmp_path):
        """Fetch generic exception returns False."""
        repo = BareGitRepo(tmp_path / ".dotfiles", tmp_path)

        with patch.object(repo, "ensure_fetch_refspec"):
            with patch.object(repo, "run_bare") as mock_run:
                mock_run.side_effect = Exception("Unknown error")
                result = repo.fetch()

        assert result is False


class TestGetTrackedFiles:
    """Tests for get_tracked_files method."""

    def test_returns_files_from_remote_branch(self, tmp_path):
        """Returns files from origin/branch when available."""
        repo = BareGitRepo(tmp_path / ".dotfiles", tmp_path)

        with patch.object(repo, "run_bare") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=".zshrc\n.vimrc\n.gitconfig\n"
            )
            result = repo.get_tracked_files("main")

        assert result == [".zshrc", ".vimrc", ".gitconfig"]

    def test_returns_empty_on_nonexistent_branch(self, tmp_path):
        """Returns empty list when branch doesn't exist."""
        repo = BareGitRepo(tmp_path / ".dotfiles", tmp_path)

        with patch.object(repo, "run_bare") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=128,
                stdout=""
            )
            result = repo.get_tracked_files("nonexistent")

        assert result == []

    def test_returns_empty_on_exception(self, tmp_path):
        """Returns empty list on exception."""
        repo = BareGitRepo(tmp_path / ".dotfiles", tmp_path)

        with patch.object(repo, "run_bare") as mock_run:
            mock_run.side_effect = Exception("Git error")
            result = repo.get_tracked_files("main")

        assert result == []


class TestGetCommitInfo:
    """Tests for get_commit_info method."""

    def test_returns_commit_hash(self, tmp_path):
        """Returns short commit hash for valid ref."""
        repo = BareGitRepo(tmp_path / ".dotfiles", tmp_path)

        with patch.object(repo, "run_bare") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="abc1234\n"
            )
            result = repo.get_commit_info("HEAD")

        assert result == "abc1234"

    def test_returns_none_for_invalid_ref(self, tmp_path):
        """Returns None when ref doesn't exist."""
        repo = BareGitRepo(tmp_path / ".dotfiles", tmp_path)

        with patch.object(repo, "run_bare") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=128,
                stdout=""
            )
            result = repo.get_commit_info("nonexistent")

        assert result is None

    def test_returns_none_on_exception(self, tmp_path):
        """Returns None on exception."""
        repo = BareGitRepo(tmp_path / ".dotfiles", tmp_path)

        with patch.object(repo, "run_bare") as mock_run:
            mock_run.side_effect = Exception("Git error")
            result = repo.get_commit_info("HEAD")

        assert result is None


class TestGetAheadBehind:
    """Tests for get_ahead_behind method."""

    def test_returns_ahead_behind_counts(self, tmp_path):
        """Returns tuple of (ahead, behind) counts."""
        repo = BareGitRepo(tmp_path / ".dotfiles", tmp_path)

        with patch.object(repo, "run_bare") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="3\t1\n"
            )
            ahead, behind = repo.get_ahead_behind("main", "origin/main")

        assert ahead == 3
        assert behind == 1

    def test_returns_zeros_on_error(self, tmp_path):
        """Returns (0, 0) on error."""
        repo = BareGitRepo(tmp_path / ".dotfiles", tmp_path)

        with patch.object(repo, "run_bare") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=128,
                stdout=""
            )
            ahead, behind = repo.get_ahead_behind("main", "origin/main")

        assert ahead == 0
        assert behind == 0

    def test_returns_zeros_on_exception(self, tmp_path):
        """Returns (0, 0) on exception."""
        repo = BareGitRepo(tmp_path / ".dotfiles", tmp_path)

        with patch.object(repo, "run_bare") as mock_run:
            mock_run.side_effect = Exception("Git error")
            ahead, behind = repo.get_ahead_behind("main", "origin/main")

        assert ahead == 0
        assert behind == 0


class TestBranchExists:
    """Tests for branch_exists method."""

    def test_local_branch_exists(self, tmp_path):
        """Returns True when local branch exists."""
        repo = BareGitRepo(tmp_path / ".dotfiles", tmp_path)

        with patch.object(repo, "run_bare") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = repo.branch_exists("main")

        assert result is True

    def test_remote_branch_exists(self, tmp_path):
        """Returns True when only remote branch exists."""
        repo = BareGitRepo(tmp_path / ".dotfiles", tmp_path)

        with patch.object(repo, "run_bare") as mock_run:
            # First call (local) fails, second call (remote) succeeds
            mock_run.side_effect = [
                MagicMock(returncode=1),
                MagicMock(returncode=0),
            ]
            result = repo.branch_exists("feature")

        assert result is True

    def test_no_branch_exists(self, tmp_path):
        """Returns False when branch doesn't exist."""
        repo = BareGitRepo(tmp_path / ".dotfiles", tmp_path)

        with patch.object(repo, "run_bare") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            result = repo.branch_exists("nonexistent")

        assert result is False

    def test_exception_returns_false(self, tmp_path):
        """Returns False on exception."""
        repo = BareGitRepo(tmp_path / ".dotfiles", tmp_path)

        with patch.object(repo, "run_bare") as mock_run:
            mock_run.side_effect = Exception("Git error")
            result = repo.branch_exists("main")

        assert result is False


class TestGetChangedFiles:
    """Tests for get_changed_files method."""

    def test_returns_changed_files(self, tmp_path):
        """Returns list of changed files."""
        repo = BareGitRepo(tmp_path / ".dotfiles", tmp_path)

        with patch.object(repo, "run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=".zshrc\n.vimrc\n",
                stderr=""
            )
            result = repo.get_changed_files()

        assert result == [".zshrc", ".vimrc"]

    def test_returns_empty_on_failure(self, tmp_path):
        """Returns empty list when git diff fails."""
        repo = BareGitRepo(tmp_path / ".dotfiles", tmp_path)

        with patch.object(repo, "run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="error"
            )
            result = repo.get_changed_files()

        assert result == []

    def test_returns_empty_on_exception(self, tmp_path):
        """Returns empty list on exception."""
        repo = BareGitRepo(tmp_path / ".dotfiles", tmp_path)

        with patch.object(repo, "run") as mock_run:
            mock_run.side_effect = Exception("Git error")
            result = repo.get_changed_files()

        assert result == []


class TestGetHeadBranch:
    """Tests for get_head_branch method."""

    def test_returns_branch_name(self, tmp_path):
        """Returns current HEAD branch name."""
        repo = BareGitRepo(tmp_path / ".dotfiles", tmp_path)

        with patch.object(repo, "run_bare") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="main\n"
            )
            result = repo.get_head_branch()

        assert result == "main"

    def test_returns_none_on_detached_head(self, tmp_path):
        """Returns None when HEAD is detached."""
        repo = BareGitRepo(tmp_path / ".dotfiles", tmp_path)

        with patch.object(repo, "run_bare") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=128,
                stdout=""
            )
            result = repo.get_head_branch()

        assert result is None

    def test_returns_none_on_exception(self, tmp_path):
        """Returns None on exception."""
        repo = BareGitRepo(tmp_path / ".dotfiles", tmp_path)

        with patch.object(repo, "run_bare") as mock_run:
            mock_run.side_effect = Exception("Git error")
            result = repo.get_head_branch()

        assert result is None


class TestGetAvailableBranches:
    """Tests for get_available_branches method."""

    def test_combines_local_and_remote_branches(self, tmp_path):
        """Returns combined list of local and remote branches."""
        repo = BareGitRepo(tmp_path / ".dotfiles", tmp_path)

        with patch.object(repo, "run_bare") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="main\nfeature\n"),
                MagicMock(returncode=0, stdout="origin/main\norigin/dev\n"),
            ]
            result = repo.get_available_branches()

        assert sorted(result) == ["dev", "feature", "main"]

    def test_returns_empty_on_exception(self, tmp_path):
        """Returns empty list on exception."""
        repo = BareGitRepo(tmp_path / ".dotfiles", tmp_path)

        with patch.object(repo, "run_bare") as mock_run:
            mock_run.side_effect = Exception("Git error")
            result = repo.get_available_branches()

        assert result == []


class TestSetupBranch:
    """Tests for setup_branch method."""

    def test_setup_branch_success(self, tmp_path):
        """Sets up branch tracking successfully."""
        repo = BareGitRepo(tmp_path / ".dotfiles", tmp_path)

        with patch.object(repo, "fetch"):
            with patch.object(repo, "run_bare") as mock_bare:
                mock_bare.return_value = MagicMock(returncode=0)
                repo.setup_branch("main")

        # Should have called run_bare multiple times
        assert mock_bare.call_count >= 2

    def test_setup_branch_remote_not_found(self, tmp_path):
        """Handles missing remote branch."""
        repo = BareGitRepo(tmp_path / ".dotfiles", tmp_path)

        with patch.object(repo, "fetch"):
            with patch.object(repo, "run_bare") as mock_bare:
                # show-ref returns non-zero (branch not found)
                mock_bare.return_value = MagicMock(returncode=1)
                # Should not raise
                repo.setup_branch("nonexistent")

    def test_setup_branch_exception_handled(self, tmp_path):
        """Handles exceptions gracefully."""
        repo = BareGitRepo(tmp_path / ".dotfiles", tmp_path)

        with patch.object(repo, "fetch"):
            with patch.object(repo, "run_bare") as mock_bare:
                mock_bare.side_effect = Exception("Git error")
                # Should not raise
                repo.setup_branch("main")
