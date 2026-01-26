"""Tests for DotfilesManager class."""

from unittest.mock import MagicMock, patch

import pytest

from freckle.dotfiles.manager import DotfilesManager


class TestDotfilesManagerInit:
    """Tests for DotfilesManager initialization."""

    def test_init_sets_attributes(self, tmp_path):
        """Initializes with correct attributes."""
        manager = DotfilesManager(
            repo_url="https://github.com/user/dotfiles.git",
            dotfiles_dir=tmp_path / ".dotfiles",
            work_tree=tmp_path / "home",
            branch="main"
        )

        assert manager.repo_url == "https://github.com/user/dotfiles.git"
        assert manager.dotfiles_dir == tmp_path / ".dotfiles"
        assert manager.work_tree == tmp_path / "home"
        assert manager.branch == "main"


class TestGetTrackedFiles:
    """Tests for get_tracked_files method."""

    def test_returns_empty_when_repo_not_exists(self, tmp_path):
        """Returns empty list when repo doesn't exist."""
        manager = DotfilesManager(
            repo_url="https://github.com/user/dotfiles.git",
            dotfiles_dir=tmp_path / ".dotfiles",
            work_tree=tmp_path,
            branch="main"
        )

        result = manager.get_tracked_files()

        assert result == []

    def test_returns_tracked_files(self, tmp_path):
        """Returns list of tracked files."""
        dotfiles_dir = tmp_path / ".dotfiles"
        dotfiles_dir.mkdir()

        manager = DotfilesManager(
            repo_url="https://github.com/user/dotfiles.git",
            dotfiles_dir=dotfiles_dir,
            work_tree=tmp_path,
            branch="main"
        )

        with patch.object(manager, "_resolve_branch") as mock_resolve:
            mock_resolve.return_value = {
                "configured": "main",
                "effective": "main",
                "reason": "configured"
            }
            with patch.object(
                manager._git, "get_tracked_files"
            ) as mock_tracked:
                mock_tracked.return_value = [".zshrc", ".vimrc"]
                result = manager.get_tracked_files()

        assert result == [".zshrc", ".vimrc"]


class TestGetDetailedStatus:
    """Tests for get_detailed_status method."""

    def test_not_initialized(self, tmp_path):
        """Returns initialized=False when repo doesn't exist."""
        manager = DotfilesManager(
            repo_url="https://github.com/user/dotfiles.git",
            dotfiles_dir=tmp_path / ".dotfiles",
            work_tree=tmp_path,
            branch="main"
        )

        status = manager.get_detailed_status()

        assert status["initialized"] is False

    def test_offline_mode_skips_fetch(self, tmp_path):
        """Offline mode skips fetch."""
        dotfiles_dir = tmp_path / ".dotfiles"
        dotfiles_dir.mkdir()

        manager = DotfilesManager(
            repo_url="https://github.com/user/dotfiles.git",
            dotfiles_dir=dotfiles_dir,
            work_tree=tmp_path,
            branch="main"
        )

        with patch.object(manager._git, "fetch") as mock_fetch:
            with patch.object(manager, "_resolve_branch") as mock_resolve:
                mock_resolve.return_value = {
                    "configured": "main",
                    "effective": "main",
                    "reason": "configured"
                }
                with patch.object(manager._git, "get_changed_files") as m_ch:
                    m_ch.return_value = []
                    with patch.object(manager._git, "get_commit_info") as m_ci:
                        m_ci.return_value = "abc1234"
                        with patch.object(
                            manager._git, "get_ahead_behind"
                        ) as m_ab:
                            m_ab.return_value = (0, 0)
                            manager.get_detailed_status(offline=True)

        mock_fetch.assert_not_called()

    def test_fetch_failure_is_recorded(self, tmp_path):
        """Records fetch failure in status."""
        dotfiles_dir = tmp_path / ".dotfiles"
        dotfiles_dir.mkdir()

        manager = DotfilesManager(
            repo_url="https://github.com/user/dotfiles.git",
            dotfiles_dir=dotfiles_dir,
            work_tree=tmp_path,
            branch="main"
        )

        with patch.object(manager._git, "fetch", return_value=False):
            with patch.object(manager, "_resolve_branch") as mock_resolve:
                mock_resolve.return_value = {
                    "configured": "main",
                    "effective": "main",
                    "reason": "configured"
                }
                with patch.object(manager._git, "get_changed_files") as m_ch:
                    m_ch.return_value = []
                    with patch.object(manager._git, "get_commit_info") as m_ci:
                        m_ci.return_value = "abc1234"
                        with patch.object(
                            manager._git, "get_ahead_behind"
                        ) as m_ab:
                            m_ab.return_value = (0, 0)
                            status = manager.get_detailed_status()

        assert status["fetch_failed"] is True

    def test_local_commit_none(self, tmp_path):
        """Handles case when local commit is None."""
        dotfiles_dir = tmp_path / ".dotfiles"
        dotfiles_dir.mkdir()

        manager = DotfilesManager(
            repo_url="https://github.com/user/dotfiles.git",
            dotfiles_dir=dotfiles_dir,
            work_tree=tmp_path,
            branch="main"
        )

        with patch.object(manager._git, "fetch", return_value=True):
            with patch.object(manager, "_resolve_branch") as mock_resolve:
                mock_resolve.return_value = {
                    "configured": "main",
                    "effective": "main",
                    "reason": "configured"
                }
                with patch.object(manager._git, "get_changed_files") as m_ch:
                    m_ch.return_value = []
                    with patch.object(manager._git, "get_commit_info") as m_ci:
                        m_ci.side_effect = [None, "abc1234"]
                        status = manager.get_detailed_status()

        assert status["local_commit"] is None
        assert status["remote_commit"] == "abc1234"

    def test_remote_commit_none(self, tmp_path):
        """Handles case when remote commit is None."""
        dotfiles_dir = tmp_path / ".dotfiles"
        dotfiles_dir.mkdir()

        manager = DotfilesManager(
            repo_url="https://github.com/user/dotfiles.git",
            dotfiles_dir=dotfiles_dir,
            work_tree=tmp_path,
            branch="main"
        )

        with patch.object(manager._git, "fetch", return_value=True):
            with patch.object(manager, "_resolve_branch") as mock_resolve:
                mock_resolve.return_value = {
                    "configured": "main",
                    "effective": "main",
                    "reason": "configured"
                }
                with patch.object(manager._git, "get_changed_files") as m_ch:
                    m_ch.return_value = []
                    with patch.object(manager._git, "get_commit_info") as m_ci:
                        m_ci.side_effect = ["abc1234", None]
                        status = manager.get_detailed_status()

        assert status["local_commit"] == "abc1234"
        assert status["remote_commit"] is None
        assert status.get("remote_branch_missing") is True


class TestGetFileSyncStatus:
    """Tests for get_file_sync_status method."""

    def test_not_initialized(self, tmp_path):
        """Returns 'not-initialized' when repo doesn't exist."""
        manager = DotfilesManager(
            repo_url="https://github.com/user/dotfiles.git",
            dotfiles_dir=tmp_path / ".dotfiles",
            work_tree=tmp_path,
            branch="main"
        )

        result = manager.get_file_sync_status(".zshrc")

        assert result == "not-initialized"

    def test_not_found(self, tmp_path):
        """Returns 'not-found' when file doesn't exist and not tracked."""
        dotfiles_dir = tmp_path / ".dotfiles"
        dotfiles_dir.mkdir()

        manager = DotfilesManager(
            repo_url="https://github.com/user/dotfiles.git",
            dotfiles_dir=dotfiles_dir,
            work_tree=tmp_path,
            branch="main"
        )

        with patch.object(manager, "_resolve_branch") as mock_resolve:
            mock_resolve.return_value = {
                "configured": "main",
                "effective": "main",
                "reason": "configured"
            }
            with patch.object(manager._git, "get_tracked_files") as mock_t:
                mock_t.return_value = []
                result = manager.get_file_sync_status(".zshrc")

        assert result == "not-found"

    def test_missing(self, tmp_path):
        """Returns 'missing' when tracked file doesn't exist locally."""
        dotfiles_dir = tmp_path / ".dotfiles"
        dotfiles_dir.mkdir()

        manager = DotfilesManager(
            repo_url="https://github.com/user/dotfiles.git",
            dotfiles_dir=dotfiles_dir,
            work_tree=tmp_path,
            branch="main"
        )

        with patch.object(manager, "_resolve_branch") as mock_resolve:
            mock_resolve.return_value = {
                "configured": "main",
                "effective": "main",
                "reason": "configured"
            }
            with patch.object(manager._git, "get_tracked_files") as mock_t:
                mock_t.return_value = [".zshrc"]
                result = manager.get_file_sync_status(".zshrc")

        assert result == "missing"

    def test_untracked(self, tmp_path):
        """Returns 'untracked' when file exists but not tracked."""
        dotfiles_dir = tmp_path / ".dotfiles"
        dotfiles_dir.mkdir()
        (tmp_path / ".zshrc").write_text("# zshrc")

        manager = DotfilesManager(
            repo_url="https://github.com/user/dotfiles.git",
            dotfiles_dir=dotfiles_dir,
            work_tree=tmp_path,
            branch="main"
        )

        with patch.object(manager, "_resolve_branch") as mock_resolve:
            mock_resolve.return_value = {
                "configured": "main",
                "effective": "main",
                "reason": "configured"
            }
            with patch.object(manager._git, "get_tracked_files") as mock_t:
                mock_t.return_value = []
                result = manager.get_file_sync_status(".zshrc")

        assert result == "untracked"

    def test_modified(self, tmp_path):
        """Returns 'modified' when file has local changes."""
        dotfiles_dir = tmp_path / ".dotfiles"
        dotfiles_dir.mkdir()
        (tmp_path / ".zshrc").write_text("# modified zshrc")

        manager = DotfilesManager(
            repo_url="https://github.com/user/dotfiles.git",
            dotfiles_dir=dotfiles_dir,
            work_tree=tmp_path,
            branch="main"
        )

        with patch.object(manager, "_resolve_branch") as mock_resolve:
            mock_resolve.return_value = {
                "configured": "main",
                "effective": "main",
                "reason": "configured"
            }
            with patch.object(manager._git, "get_tracked_files") as mock_t:
                mock_t.return_value = [".zshrc"]
                with patch.object(manager._git, "run") as mock_run:
                    # diff returns non-zero when there are changes
                    mock_run.return_value = MagicMock(returncode=1)
                    result = manager.get_file_sync_status(".zshrc")

        assert result == "modified"

    def test_up_to_date(self, tmp_path):
        """Returns 'up-to-date' when file matches HEAD."""
        dotfiles_dir = tmp_path / ".dotfiles"
        dotfiles_dir.mkdir()
        (tmp_path / ".zshrc").write_text("# zshrc")

        manager = DotfilesManager(
            repo_url="https://github.com/user/dotfiles.git",
            dotfiles_dir=dotfiles_dir,
            work_tree=tmp_path,
            branch="main"
        )

        with patch.object(manager, "_resolve_branch") as mock_resolve:
            mock_resolve.return_value = {
                "configured": "main",
                "effective": "main",
                "reason": "configured"
            }
            with patch.object(manager._git, "get_tracked_files") as mock_t:
                mock_t.return_value = [".zshrc"]
                with patch.object(manager._git, "run") as mock_run:
                    mock_run.return_value = MagicMock(returncode=0)
                    with patch.object(manager._git, "run_bare") as mock_bare:
                        mock_bare.return_value = MagicMock(returncode=0)
                        result = manager.get_file_sync_status(".zshrc")

        assert result == "up-to-date"

    def test_error_on_exception(self, tmp_path):
        """Returns 'error' on exception."""
        dotfiles_dir = tmp_path / ".dotfiles"
        dotfiles_dir.mkdir()
        (tmp_path / ".zshrc").write_text("# zshrc")

        manager = DotfilesManager(
            repo_url="https://github.com/user/dotfiles.git",
            dotfiles_dir=dotfiles_dir,
            work_tree=tmp_path,
            branch="main"
        )

        with patch.object(manager, "_resolve_branch") as mock_resolve:
            mock_resolve.return_value = {
                "configured": "main",
                "effective": "main",
                "reason": "configured"
            }
            with patch.object(manager._git, "get_tracked_files") as mock_t:
                mock_t.return_value = [".zshrc"]
                with patch.object(manager._git, "run") as mock_run:
                    mock_run.side_effect = Exception("Git error")
                    result = manager.get_file_sync_status(".zshrc")

        assert result == "error"

    def test_up_to_date_when_remote_ref_missing(self, tmp_path):
        """Returns 'up-to-date' when remote ref doesn't exist."""
        dotfiles_dir = tmp_path / ".dotfiles"
        dotfiles_dir.mkdir()
        (tmp_path / ".zshrc").write_text("# zshrc")

        manager = DotfilesManager(
            repo_url="https://github.com/user/dotfiles.git",
            dotfiles_dir=dotfiles_dir,
            work_tree=tmp_path,
            branch="main"
        )

        with patch.object(manager, "_resolve_branch") as mock_resolve:
            mock_resolve.return_value = {
                "configured": "main",
                "effective": "main",
                "reason": "configured"
            }
            with patch.object(manager._git, "get_tracked_files") as mock_t:
                mock_t.return_value = [".zshrc"]
                with patch.object(manager._git, "run") as mock_run:
                    # File matches HEAD
                    mock_run.return_value = MagicMock(returncode=0)
                    with patch.object(manager._git, "run_bare") as mock_bare:
                        # Remote ref doesn't exist
                        mock_bare.return_value = MagicMock(returncode=1)
                        result = manager.get_file_sync_status(".zshrc")

        assert result == "up-to-date"

    def test_behind_when_differs_from_remote(self, tmp_path):
        """Returns 'behind' when file differs from remote."""
        dotfiles_dir = tmp_path / ".dotfiles"
        dotfiles_dir.mkdir()
        (tmp_path / ".zshrc").write_text("# zshrc")

        manager = DotfilesManager(
            repo_url="https://github.com/user/dotfiles.git",
            dotfiles_dir=dotfiles_dir,
            work_tree=tmp_path,
            branch="main"
        )

        with patch.object(manager, "_resolve_branch") as mock_resolve:
            mock_resolve.return_value = {
                "configured": "main",
                "effective": "main",
                "reason": "configured"
            }
            with patch.object(manager._git, "get_tracked_files") as mock_t:
                mock_t.return_value = [".zshrc"]
                with patch.object(manager._git, "run") as mock_run:
                    mock_run.side_effect = [
                        MagicMock(returncode=0),  # diff HEAD - no changes
                        MagicMock(returncode=1),  # diff remote - has changes
                        MagicMock(returncode=1),  # diff HEAD remote - behind
                    ]
                    with patch.object(manager._git, "run_bare") as mock_bare:
                        # Remote ref exists
                        mock_bare.return_value = MagicMock(returncode=0)
                        result = manager.get_file_sync_status(".zshrc")

        assert result == "behind"


class TestCommitAndPush:
    """Tests for commit_and_push method."""

    def test_branch_not_found_returns_error(self, tmp_path):
        """Returns error when branch not found."""
        dotfiles_dir = tmp_path / ".dotfiles"
        dotfiles_dir.mkdir()

        manager = DotfilesManager(
            repo_url="https://github.com/user/dotfiles.git",
            dotfiles_dir=dotfiles_dir,
            work_tree=tmp_path,
            branch="main"
        )

        with patch.object(manager, "_resolve_branch") as mock_resolve:
            mock_resolve.return_value = {
                "configured": "main",
                "effective": "main",
                "reason": "not_found",
                "message": "Branch not found"
            }
            result = manager.commit_and_push("Test commit")

        assert result["success"] is False
        assert "not found" in result["error"].lower()

    def test_success_delegates_to_operations(self, tmp_path):
        """Delegates to operations.commit_and_push on success."""
        dotfiles_dir = tmp_path / ".dotfiles"
        dotfiles_dir.mkdir()

        manager = DotfilesManager(
            repo_url="https://github.com/user/dotfiles.git",
            dotfiles_dir=dotfiles_dir,
            work_tree=tmp_path,
            branch="main"
        )

        with patch.object(manager, "_resolve_branch") as mock_resolve:
            mock_resolve.return_value = {
                "configured": "main",
                "effective": "main",
                "reason": "configured"
            }
            with patch(
                "freckle.dotfiles.manager.operations.commit_and_push"
            ) as mock_op:
                mock_op.return_value = {
                    "success": True,
                    "committed": True,
                    "pushed": True
                }
                result = manager.commit_and_push("Test commit")

        assert result["success"] is True
        mock_op.assert_called_once()


class TestPush:
    """Tests for push method."""

    def test_push_delegates_to_operations(self, tmp_path):
        """Delegates to operations.push."""
        dotfiles_dir = tmp_path / ".dotfiles"
        dotfiles_dir.mkdir()

        manager = DotfilesManager(
            repo_url="https://github.com/user/dotfiles.git",
            dotfiles_dir=dotfiles_dir,
            work_tree=tmp_path,
            branch="main"
        )

        with patch.object(manager, "_resolve_branch") as mock_resolve:
            mock_resolve.return_value = {
                "configured": "main",
                "effective": "main",
                "reason": "configured"
            }
            with patch(
                "freckle.dotfiles.manager.operations.push"
            ) as mock_push:
                mock_push.return_value = {"success": True, "error": None}
                result = manager.push()

        assert result["success"] is True
        mock_push.assert_called_once()


class TestForceCheckout:
    """Tests for force_checkout method."""

    def test_force_checkout_delegates_to_operations(self, tmp_path):
        """Delegates to operations.force_checkout."""
        dotfiles_dir = tmp_path / ".dotfiles"
        dotfiles_dir.mkdir()

        manager = DotfilesManager(
            repo_url="https://github.com/user/dotfiles.git",
            dotfiles_dir=dotfiles_dir,
            work_tree=tmp_path,
            branch="main"
        )

        with patch.object(manager, "_resolve_branch") as mock_resolve:
            mock_resolve.return_value = {
                "configured": "main",
                "effective": "main",
                "reason": "configured"
            }
            with patch(
                "freckle.dotfiles.manager.operations.force_checkout"
            ) as mock_fc:
                manager.force_checkout()

        mock_fc.assert_called_once()


class TestCheckoutToWorktree:
    """Tests for _checkout_to_worktree method."""

    def test_checkout_failure_raises(self, tmp_path):
        """Raises RuntimeError when checkout fails."""
        dotfiles_dir = tmp_path / ".dotfiles"
        dotfiles_dir.mkdir()

        manager = DotfilesManager(
            repo_url="https://github.com/user/dotfiles.git",
            dotfiles_dir=dotfiles_dir,
            work_tree=tmp_path,
            branch="main"
        )

        with patch.object(manager._git, "run") as mock_run:
            mock_run.side_effect = Exception("Checkout error")
            with pytest.raises(RuntimeError, match="Checkout failed"):
                manager._checkout_to_worktree("main")


class TestSetup:
    """Tests for setup method."""

    def test_setup_when_dir_exists_returns_early(self, tmp_path):
        """Returns early when dotfiles_dir already exists."""
        dotfiles_dir = tmp_path / ".dotfiles"
        dotfiles_dir.mkdir()

        manager = DotfilesManager(
            repo_url="https://github.com/user/dotfiles.git",
            dotfiles_dir=dotfiles_dir,
            work_tree=tmp_path,
            branch="main"
        )

        with patch.object(manager._git, "clone_bare") as mock_clone:
            manager.setup()
            mock_clone.assert_not_called()


class TestCreateNew:
    """Tests for create_new method."""

    def test_raises_if_dir_exists(self, tmp_path):
        """Raises RuntimeError if directory exists."""
        dotfiles_dir = tmp_path / ".dotfiles"
        dotfiles_dir.mkdir()

        manager = DotfilesManager(
            repo_url="https://github.com/user/dotfiles.git",
            dotfiles_dir=dotfiles_dir,
            work_tree=tmp_path,
            branch="main"
        )

        with pytest.raises(RuntimeError, match="already exists"):
            manager.create_new()

    def test_creates_empty_repo(self, tmp_path):
        """Creates empty repository with initial commit."""
        manager = DotfilesManager(
            repo_url="https://github.com/user/dotfiles.git",
            dotfiles_dir=tmp_path / ".dotfiles",
            work_tree=tmp_path,
            branch="main"
        )

        with patch.object(manager._git, "init_bare") as mock_init:
            with patch.object(manager._git, "run_bare") as mock_bare:
                mock_bare.return_value = MagicMock(returncode=0)
                with patch.object(manager._git, "run") as mock_run:
                    mock_run.return_value = MagicMock(returncode=0)
                    manager.create_new()

        mock_init.assert_called_once_with(initial_branch="main")

    def test_adds_initial_files(self, tmp_path):
        """Adds initial files when provided."""
        (tmp_path / ".zshrc").write_text("# zshrc")

        manager = DotfilesManager(
            repo_url="https://github.com/user/dotfiles.git",
            dotfiles_dir=tmp_path / ".dotfiles",
            work_tree=tmp_path,
            branch="main"
        )

        with patch.object(manager._git, "init_bare"):
            with patch.object(manager._git, "run_bare") as mock_bare:
                mock_bare.return_value = MagicMock(returncode=0)
                with patch.object(manager._git, "run") as mock_run:
                    mock_run.return_value = MagicMock(returncode=0)
                    manager.create_new(initial_files=[".zshrc"])

        # Should have called run with "add" for the file
        add_calls = [c for c in mock_run.call_args_list if "add" in c[0]]
        assert len(add_calls) > 0

    def test_configures_remote(self, tmp_path):
        """Configures remote when URL provided."""
        manager = DotfilesManager(
            repo_url="https://github.com/user/dotfiles.git",
            dotfiles_dir=tmp_path / ".dotfiles",
            work_tree=tmp_path,
            branch="main"
        )

        with patch.object(manager._git, "init_bare"):
            with patch.object(manager._git, "run_bare") as mock_bare:
                mock_bare.return_value = MagicMock(returncode=0)
                with patch.object(manager._git, "run") as mock_run:
                    mock_run.return_value = MagicMock(returncode=0)
                    with patch.object(manager._git, "ensure_fetch_refspec"):
                        manager.create_new(
                            remote_url="git@github.com:user/dotfiles.git"
                        )

        # Should have called run_bare with "remote" "add"
        remote_calls = [
            c for c in mock_bare.call_args_list
            if len(c[0]) > 1 and c[0][0] == "remote"
        ]
        assert len(remote_calls) > 0

    def test_push_failure_logs_warning(self, tmp_path):
        """Logs warning when push fails."""
        manager = DotfilesManager(
            repo_url="https://github.com/user/dotfiles.git",
            dotfiles_dir=tmp_path / ".dotfiles",
            work_tree=tmp_path,
            branch="main"
        )

        with patch.object(manager._git, "init_bare"):
            with patch.object(manager._git, "run_bare") as mock_bare:
                # First calls succeed, push fails
                mock_bare.side_effect = [
                    MagicMock(returncode=0),  # config
                    MagicMock(returncode=0),  # remote add
                    MagicMock(returncode=1, stderr="push rejected"),  # push
                ]
                with patch.object(manager._git, "run") as mock_run:
                    mock_run.return_value = MagicMock(returncode=0)
                    with patch.object(manager._git, "ensure_fetch_refspec"):
                        # Should not raise, just log warning
                        manager.create_new(
                            remote_url="git@github.com:user/dotfiles.git"
                        )

    def test_push_exception_logs_warning(self, tmp_path):
        """Logs warning when push raises exception."""
        manager = DotfilesManager(
            repo_url="https://github.com/user/dotfiles.git",
            dotfiles_dir=tmp_path / ".dotfiles",
            work_tree=tmp_path,
            branch="main"
        )

        with patch.object(manager._git, "init_bare"):
            with patch.object(manager._git, "run_bare") as mock_bare:
                # First calls succeed, push raises
                mock_bare.side_effect = [
                    MagicMock(returncode=0),  # config
                    MagicMock(returncode=0),  # remote add
                    Exception("Network error"),  # push
                ]
                with patch.object(manager._git, "run") as mock_run:
                    mock_run.return_value = MagicMock(returncode=0)
                    with patch.object(manager._git, "ensure_fetch_refspec"):
                        # Should not raise, just log warning
                        manager.create_new(
                            remote_url="git@github.com:user/dotfiles.git"
                        )
