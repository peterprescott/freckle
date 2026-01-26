"""High-level dotfiles management operations."""

import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from . import operations
from .branch import BranchResolver
from .repo import BareGitRepo
from .types import (
    AddFilesResult,
    BranchInfo,
    CommitPushResult,
    SyncStatus,
)

logger = logging.getLogger(__name__)


class DotfilesManager:
    """Manages dotfiles using a bare git repository with a separate work tree.

    This implements the "bare repo" pattern for dotfiles:
    - The git repository is stored in a bare format (e.g., ~/.dotfiles)
    - The work tree is the user's home directory
    - This allows tracking dotfiles without polluting $HOME with .git
    """

    def __init__(
        self,
        repo_url: str,
        dotfiles_dir: Path,
        work_tree: Path,
        branch: str = "main",
    ):
        self.repo_url = repo_url
        self.dotfiles_dir = Path(dotfiles_dir)
        self.work_tree = Path(work_tree)
        self.branch = branch
        self._git = BareGitRepo(self.dotfiles_dir, self.work_tree)

    def _resolve_branch(self) -> BranchInfo:
        """Resolve which branch to use, with detailed context."""
        resolver = BranchResolver(
            configured_branch=self.branch,
            get_available=self._git.get_available_branches,
            get_head=self._git.get_head_branch,
        )
        return resolver.resolve()

    def _find_existing_files(self, tracked_files: List[str]) -> List[str]:
        """Find which tracked files already exist in the work tree."""
        existing = []
        for file_path in tracked_files:
            local_path = self.work_tree / file_path
            if local_path.exists() and local_path.is_file():
                existing.append(file_path)
        return existing

    def _backup_files(self, file_paths: List[str]) -> Optional[Path]:
        """Move files to a timestamped backup directory."""
        if not file_paths:
            return None

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = self.work_tree / f".dotfiles_backup_{timestamp}"
        backup_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            f"Backing up {len(file_paths)} existing files to {backup_dir}"
        )
        for file_path in file_paths:
            src = self.work_tree / file_path
            dst = backup_dir / file_path
            if src.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst))

        return backup_dir

    def _checkout_to_worktree(self, branch: str, force: bool = False):
        """Checkout files to the work tree directory."""
        try:
            args = ["checkout"]
            if force:
                args.append("-f")
            args.append(branch)

            self._git.run(*args)
        except Exception as e:
            raise RuntimeError(f"Checkout failed: {e}")

    def get_tracked_files(self) -> List[str]:
        """Get list of all files tracked in the dotfiles repository."""
        if not self.dotfiles_dir.exists():
            return []

        branch_info = self._resolve_branch()
        return self._git.get_tracked_files(branch_info["effective"])

    def setup(self):
        """Clone repo and checkout dotfiles to home directory."""
        if self.dotfiles_dir.exists():
            logger.info("Dotfiles repository already exists")
            return

        # Clone bare repo
        self._git.clone_bare(self.repo_url)

        # Resolve branch
        branch_info = self._resolve_branch()
        effective_branch = branch_info["effective"]

        # Set up branch tracking
        self._git.setup_branch(effective_branch)

        # Find files that would conflict
        tracked = self._git.get_tracked_files(effective_branch)
        existing = self._find_existing_files(tracked)

        # Backup any existing files
        backup_dir = self._backup_files(existing)
        if backup_dir:
            logger.info(f"Backed up existing files to {backup_dir}")

        # Checkout
        self._checkout_to_worktree(effective_branch, force=True)
        logger.info("Checkout complete!")

    def create_new(
        self,
        initial_files: Optional[List[str]] = None,
        remote_url: Optional[str] = None,
    ):
        """Create a new dotfiles repository from scratch.

        Args:
            initial_files: Files (relative to work_tree) to track
            remote_url: Optional remote URL to configure as origin
        """
        if self.dotfiles_dir.exists():
            raise RuntimeError(
                f"Directory already exists: {self.dotfiles_dir}"
            )

        # Initialize bare repo
        self._git.init_bare(initial_branch=self.branch)

        # Configure to not show untracked files
        self._git.run_bare(
            "config", "--local", "status.showUntrackedFiles", "no"
        )

        # Add remote if provided
        if remote_url:
            self._git.run_bare("remote", "add", "origin", remote_url)
            self._git.ensure_fetch_refspec()

        # Add initial files if any
        if initial_files:
            for file_path in initial_files:
                full_path = self.work_tree / file_path
                if full_path.exists():
                    self._git.run("add", file_path)

            self._git.run("commit", "-m", "Initial dotfiles commit")
            logger.info(
                f"Created initial commit with {len(initial_files)} file(s)"
            )
        else:
            self._git.run(
                "commit",
                "--allow-empty",
                "-m",
                "Initialize dotfiles repository",
            )
            logger.info("Created empty initial commit")

        # Push to remote if configured
        if remote_url:
            try:
                result = self._git.run_bare(
                    "push",
                    "-u",
                    "origin",
                    self.branch,
                    check=False,
                    timeout=60,
                )
                if result.returncode == 0:
                    logger.info(f"Pushed to origin/{self.branch}")
                else:
                    logger.warning(
                        f"Could not push to remote: {result.stderr.strip()}"
                    )
            except Exception as e:
                logger.warning(f"Could not push to remote: {e}")

    def get_detailed_status(self, offline: bool = False) -> SyncStatus:
        """Get detailed sync status of the dotfiles repository."""
        if not self.dotfiles_dir.exists():
            return {"initialized": False}

        fetch_failed = False
        if not offline:
            fetch_failed = not self._git.fetch()

        # Resolve branch
        branch_info = self._resolve_branch()
        effective_branch = branch_info["effective"]

        # Get changed files
        changed_files = self._git.get_changed_files()

        # Get commit info
        local_commit = self._git.get_commit_info(
            f"refs/heads/{effective_branch}"
        )
        remote_commit = self._git.get_commit_info(
            f"refs/remotes/origin/{effective_branch}"
        )

        if local_commit is None:
            return {
                "initialized": True,
                "branch": effective_branch,
                "branch_info": branch_info,
                "has_local_changes": len(changed_files) > 0,
                "changed_files": changed_files,
                "is_ahead": False,
                "is_behind": False,
                "local_commit": None,
                "remote_commit": remote_commit,
                "fetch_failed": fetch_failed,
            }

        if remote_commit is None:
            return {
                "initialized": True,
                "branch": effective_branch,
                "branch_info": branch_info,
                "has_local_changes": len(changed_files) > 0,
                "changed_files": changed_files,
                "is_ahead": False,
                "is_behind": False,
                "remote_branch_missing": True,
                "local_commit": local_commit,
                "remote_commit": None,
                "fetch_failed": fetch_failed,
            }

        # Get ahead/behind
        ahead, behind = self._git.get_ahead_behind(
            f"refs/heads/{effective_branch}",
            f"refs/remotes/origin/{effective_branch}",
        )

        return {
            "initialized": True,
            "branch": effective_branch,
            "branch_info": branch_info,
            "has_local_changes": len(changed_files) > 0,
            "changed_files": changed_files,
            "is_ahead": ahead > 0,
            "is_behind": behind > 0,
            "ahead_count": ahead,
            "behind_count": behind,
            "local_commit": local_commit,
            "remote_commit": remote_commit,
            "fetch_failed": fetch_failed,
        }

    def get_file_sync_status(self, relative_path: str) -> str:
        """Get sync status of a specific file.

        Returns one of:
        - 'not-initialized': Repo doesn't exist
        - 'not-found': File doesn't exist locally and isn't tracked
        - 'missing': File is tracked but doesn't exist locally
        - 'untracked': File exists locally but isn't tracked
        - 'up-to-date': File matches HEAD
        - 'modified': File has local changes
        - 'behind': File differs from remote
        - 'error': Could not determine status
        """
        if not self.dotfiles_dir.exists():
            return "not-initialized"

        local_file = self.work_tree / relative_path

        # Resolve branch
        branch_info = self._resolve_branch()
        effective_branch = branch_info["effective"]

        # Check if tracked
        tracked_files = self._git.get_tracked_files(effective_branch)
        is_tracked = relative_path in tracked_files

        if not local_file.exists():
            return "missing" if is_tracked else "not-found"

        if not is_tracked:
            return "untracked"

        try:
            # Check if file differs from HEAD
            result = self._git.run(
                "diff", "--quiet", "HEAD", "--", relative_path, check=False
            )
            if result.returncode != 0:
                return "modified"

            # Check if remote branch exists
            remote_ref = f"origin/{effective_branch}"
            ref_check = self._git.run_bare(
                "show-ref",
                "--verify",
                f"refs/remotes/{remote_ref}",
                check=False,
            )
            if ref_check.returncode != 0:
                return "up-to-date"

            # Check if differs from remote
            result = self._git.run(
                "diff", "--quiet", remote_ref, "--", relative_path, check=False
            )
            if result.returncode != 0:
                result2 = self._git.run(
                    "diff",
                    "--quiet",
                    "HEAD",
                    remote_ref,
                    "--",
                    relative_path,
                    check=False,
                )
                if result2.returncode != 0:
                    return "behind"

            return "up-to-date"
        except Exception:
            return "error"

    def add_files(self, files: List[str]) -> AddFilesResult:
        """Add files to be tracked in the dotfiles repository."""
        return operations.add_files(self._git, self.work_tree, files)

    def commit_and_push(self, message: str) -> CommitPushResult:
        """Commit local changes to tracked files and push to remote."""
        branch_info = self._resolve_branch()
        effective_branch = branch_info["effective"]

        if branch_info["reason"] == "not_found":
            return {
                "success": False,
                "committed": False,
                "pushed": False,
                "error": branch_info["message"],
            }

        return operations.commit_and_push(
            self._git,
            effective_branch,
            message,
            self._git.get_changed_files,
        )

    def push(self) -> CommitPushResult:
        """Push local commits to remote."""
        branch_info = self._resolve_branch()
        return operations.push(self._git, branch_info["effective"])

    def force_checkout(self):
        """Discard local changes and update to match remote."""
        branch_info = self._resolve_branch()
        operations.force_checkout(self._git, branch_info["effective"])
