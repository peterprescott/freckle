"""Dotfiles management using the bare repository pattern."""

import logging
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

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

    def _git(
        self, *args, check: bool = True, timeout: int = 60
    ) -> subprocess.CompletedProcess:
        """Run a git command with --git-dir and --work-tree set.

        Args:
            *args: Git command arguments (e.g., "status", "--porcelain")
            check: If True, raise on non-zero exit code
            timeout: Command timeout in seconds

        Returns:
            CompletedProcess with stdout/stderr captured as text
        """
        cmd = [
            "git",
            "--git-dir",
            str(self.dotfiles_dir),
            "--work-tree",
            str(self.work_tree),
        ] + list(args)
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=check,
            cwd=str(
                self.work_tree
            ),  # Run from work_tree to ensure correct path resolution
        )

    def _git_bare(
        self, *args, check: bool = True, timeout: int = 60
    ) -> subprocess.CompletedProcess:
        """Run a git command with just --git-dir (no work tree).

        Used for operations that don't need a work tree context.
        """
        cmd = ["git", "--git-dir", str(self.dotfiles_dir)] + list(args)
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=check
        )

    def _clone_bare(self):
        """Clone the repository as a bare repo."""
        logger.info(
            f"Cloning bare repo from {self.repo_url} "
            f"to {self.dotfiles_dir}"
        )
        subprocess.run(
            ["git", "clone", "--bare", self.repo_url, str(self.dotfiles_dir)],
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )

    def _ensure_fetch_refspec(self):
        """Ensure fetch refspec is configured for remote tracking.

        Bare repos created manually often lack the fetch refspec,
        which prevents remote-tracking branches from being created.
        """
        try:
            # Check current refspecs
            result = self._git_bare(
                "config", "--get-all", "remote.origin.fetch", check=False
            )
            expected = "+refs/heads/*:refs/remotes/origin/*"

            if expected not in result.stdout:
                logger.info("Configuring fetch refspec for remote tracking")
                self._git_bare(
                    "config", "--add", "remote.origin.fetch", expected
                )
        except Exception as e:
            logger.debug(f"Could not configure fetch refspec: {e}")

    def _fetch(self) -> bool:
        """Fetch from remote origin. Returns True on success."""
        self._ensure_fetch_refspec()

        try:
            self._git_bare("fetch", "origin", timeout=60)
            return True
        except subprocess.TimeoutExpired:
            logger.warning("Fetch timed out")
            return False
        except subprocess.CalledProcessError as e:
            logger.warning(f"Fetch failed: {e.stderr.strip()}")
            return False
        except Exception as e:
            logger.warning(f"Could not fetch from remote: {e}")
            return False

    def _get_available_branches(self) -> List[str]:
        """Get list of all available branch names (local and remote)."""
        branches = set()

        try:
            # Get local branches
            result = self._git_bare(
                "for-each-ref",
                "--format=%(refname:short)",
                "refs/heads/",
                check=False,
            )
            for line in result.stdout.strip().split("\n"):
                if line.strip():
                    branches.add(line.strip())

            # Get remote branches
            result = self._git_bare(
                "for-each-ref",
                "--format=%(refname:short)",
                "refs/remotes/origin/",
                check=False,
            )
            for line in result.stdout.strip().split("\n"):
                if line.strip() and not line.strip().endswith("/HEAD"):
                    # Remove "origin/" prefix
                    branch = line.strip()
                    if branch.startswith("origin/"):
                        branch = branch[7:]
                    branches.add(branch)
        except Exception as e:
            logger.debug(f"Could not get branches: {e}")

        return sorted(branches)

    def _branch_exists(self, branch: str) -> bool:
        """Check if a branch exists locally or on remote."""
        try:
            # Check local
            result = self._git_bare(
                "show-ref", "--verify", f"refs/heads/{branch}", check=False
            )
            if result.returncode == 0:
                return True

            # Check remote
            result = self._git_bare(
                "show-ref",
                "--verify",
                f"refs/remotes/origin/{branch}",
                check=False,
            )
            return result.returncode == 0
        except Exception:
            return False

    def _get_head_branch(self) -> Optional[str]:
        """Get the current HEAD branch name."""
        try:
            result = self._git_bare(
                "symbolic-ref", "--short", "HEAD", check=False
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return None

    def _resolve_branch(self) -> Dict[str, Any]:
        """Resolve which branch to use, with detailed context.

        Returns a dict with:
        - effective: The branch to actually use
        - configured: The originally configured branch
        - reason: Why this branch was chosen
        - available: List of available branches
        - message: Human-readable explanation
        """
        configured = self.branch
        available = self._get_available_branches()

        # Check if configured branch exists
        if configured in available:
            return {
                "effective": configured,
                "configured": configured,
                "reason": "exact",
                "available": available,
                "message": None,
            }

        # Common main/master swap
        swap_map = {"main": "master", "master": "main"}
        if configured in swap_map and swap_map[configured] in available:
            swapped = swap_map[configured]
            return {
                "effective": swapped,
                "configured": configured,
                "reason": "main_master_swap",
                "available": available,
                "message": (
                    f"Branch '{configured}' not found; "
                    f"using '{swapped}' instead."
                ),
            }

        # Try HEAD
        head_branch = self._get_head_branch()
        if head_branch and head_branch in available:
            return {
                "effective": head_branch,
                "configured": configured,
                "reason": "fallback_head",
                "available": available,
                "message": (
                    f"Branch '{configured}' not found; "
                    f"using current HEAD '{head_branch}'."
                ),
            }

        # Try common defaults
        for fallback in ["main", "master"]:
            if fallback in available:
                return {
                    "effective": fallback,
                    "configured": configured,
                    "reason": "fallback_default",
                    "available": available,
                    "message": (
                        f"Branch '{configured}' not found; "
                        f"falling back to '{fallback}'."
                    ),
                }

        # Nothing found
        return {
            "effective": configured,
            "configured": configured,
            "reason": "not_found",
            "available": available,
            "message": (
                f"Branch '{configured}' not found. "
                f"Available: {', '.join(available) or '(none)'}"
            ),
        }

    def _setup_branch(self, branch: str):
        """Set up the local branch to track remote after cloning."""
        try:
            # Fetch to get remote refs
            self._fetch()

            # Check if remote branch exists
            result = self._git_bare(
                "show-ref",
                "--verify",
                f"refs/remotes/origin/{branch}",
                check=False,
            )
            if result.returncode != 0:
                logger.warning(f"Remote branch origin/{branch} not found")
                return

            # Create local branch tracking remote
            self._git_bare(
                "branch", "-f", branch, f"origin/{branch}", check=False
            )

            # Set HEAD to the branch
            self._git_bare("symbolic-ref", "HEAD", f"refs/heads/{branch}")
        except Exception as e:
            logger.warning(f"Could not set up branch: {e}")

    def _get_tracked_files(self, branch: Optional[str] = None) -> List[str]:
        """Get list of all files tracked in the target branch."""
        branch = branch or self.branch

        try:
            # Try remote branch first, then local
            for ref in [f"origin/{branch}", branch]:
                result = self._git_bare(
                    "ls-tree", "-r", "--name-only", ref, check=False
                )
                if result.returncode == 0:
                    return [
                        f.strip()
                        for f in result.stdout.strip().split("\n")
                        if f.strip()
                    ]
            return []
        except Exception as e:
            logger.warning(f"Could not get tracked files: {e}")
            return []

    def get_tracked_files(self) -> List[str]:
        """Get list of all files tracked in the dotfiles repository.

        Returns:
            List of file paths relative to home directory.
        """
        if not self.dotfiles_dir.exists():
            return []

        branch_info = self._resolve_branch()
        return self._get_tracked_files(branch=branch_info["effective"])

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

            self._git(*args)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Checkout failed: {e.stderr.strip()}")

    def setup(self):
        """Clone repo and checkout dotfiles to home directory."""
        if self.dotfiles_dir.exists():
            logger.info("Dotfiles repository already exists")
            return

        # Clone bare repo
        self._clone_bare()

        # Resolve branch
        branch_info = self._resolve_branch()
        effective_branch = branch_info["effective"]

        # Set up branch tracking
        self._setup_branch(effective_branch)

        # Find files that would conflict
        tracked = self._get_tracked_files(branch=effective_branch)
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

        # Initialize bare repo with the correct initial branch name
        logger.info(f"Creating new bare repository at {self.dotfiles_dir}")
        subprocess.run(
            [
                "git",
                "init",
                "--bare",
                f"--initial-branch={self.branch}",
                str(self.dotfiles_dir),
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        # Configure to not show untracked files (cleaner status for dotfiles)
        self._git_bare("config", "--local", "status.showUntrackedFiles", "no")

        # Add remote if provided
        if remote_url:
            self._git_bare("remote", "add", "origin", remote_url)
            # Configure fetch refspec
            self._ensure_fetch_refspec()

        # Add initial files if any
        if initial_files:
            # Add each file
            for file_path in initial_files:
                full_path = self.work_tree / file_path
                if full_path.exists():
                    self._git("add", file_path)

            # Create initial commit
            self._git("commit", "-m", "Initial dotfiles commit")
            logger.info(
                f"Created initial commit with {len(initial_files)} file(s)"
            )
        else:
            # Create empty initial commit so the branch exists
            self._git(
                "commit",
                "--allow-empty",
                "-m",
                "Initialize dotfiles repository",
            )
            logger.info("Created empty initial commit")

        # Push to remote if configured
        if remote_url:
            try:
                result = self._git_bare(
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

    def _get_changed_files(self, branch: Optional[str] = None) -> List[str]:
        """Get list of files that differ between work tree and HEAD."""
        branch = branch or self.branch

        try:
            result = self._git("diff", "--name-only", "HEAD", check=False)
            if result.returncode != 0:
                logger.warning(f"git diff failed: {result.stderr.strip()}")
                return []

            return [
                f.strip()
                for f in result.stdout.strip().split("\n")
                if f.strip()
            ]
        except Exception as e:
            logger.warning(f"Could not get changed files: {e}")
            return []

    def _get_commit_info(self, ref: str) -> Optional[str]:
        """Get short commit hash for a ref, or None if it doesn't exist."""
        try:
            result = self._git_bare("rev-parse", "--short", ref, check=False)
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return None

    def _get_ahead_behind(self, local_ref: str, remote_ref: str) -> tuple:
        """Get ahead/behind counts between two refs."""
        try:
            result = self._git_bare(
                "rev-list",
                "--count",
                "--left-right",
                f"{local_ref}...{remote_ref}",
                check=False,
            )
            if result.returncode == 0:
                parts = result.stdout.strip().split()
                if len(parts) == 2:
                    return int(parts[0]), int(parts[1])
        except Exception:
            pass
        return 0, 0

    def get_detailed_status(self, offline: bool = False) -> Dict[str, Any]:
        """Get detailed sync status of the dotfiles repository."""
        if not self.dotfiles_dir.exists():
            return {"initialized": False}

        fetch_failed = False
        if not offline:
            fetch_failed = not self._fetch()

        # Resolve branch
        branch_info = self._resolve_branch()
        effective_branch = branch_info["effective"]

        # Get changed files
        changed_files = self._get_changed_files(branch=effective_branch)

        # Get commit info
        local_commit = self._get_commit_info(f"refs/heads/{effective_branch}")
        remote_commit = self._get_commit_info(
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
        ahead, behind = self._get_ahead_behind(
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
        tracked_files = self._get_tracked_files(branch=effective_branch)
        is_tracked = relative_path in tracked_files

        if not local_file.exists():
            return "missing" if is_tracked else "not-found"

        if not is_tracked:
            return "untracked"

        try:
            # Check if file differs from HEAD
            result = self._git(
                "diff", "--quiet", "HEAD", "--", relative_path, check=False
            )
            if result.returncode != 0:
                return "modified"

            # Check if remote branch exists
            remote_ref = f"origin/{effective_branch}"
            ref_check = self._git_bare(
                "show-ref",
                "--verify",
                f"refs/remotes/{remote_ref}",
                check=False,
            )
            if ref_check.returncode != 0:
                # No remote branch - can't be behind
                return "up-to-date"

            # Check if differs from remote
            result = self._git(
                "diff", "--quiet", remote_ref, "--", relative_path, check=False
            )
            if result.returncode != 0:
                # Check if HEAD differs from remote for this file
                result2 = self._git(
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

    def add_files(self, files: List[str]) -> Dict[str, Any]:
        """Add files to be tracked in the dotfiles repository.

        Args:
            files: List of file paths relative to home directory

        Returns:
            Dictionary with result info:
            - success: Whether the operation completed
            - added: List of files successfully added
            - skipped: List of files that don't exist
            - error: Error message if operation failed
        """
        added: List[str] = []
        skipped: List[str] = []
        error: Optional[str] = None

        if not self.dotfiles_dir.exists():
            error = "Dotfiles repository not initialized"
            return {
                "success": False,
                "added": added,
                "skipped": skipped,
                "error": error,
            }

        for f in files:
            file_path = self.work_tree / f
            if not file_path.exists():
                skipped.append(f)
                continue

            try:
                add_result = self._git("add", f, check=False)
                if add_result.returncode != 0:
                    logger.warning(f"Failed to add {f}: {add_result.stderr}")
                    skipped.append(f)
                else:
                    added.append(f)
            except Exception as e:
                logger.warning(f"Error adding {f}: {e}")
                skipped.append(f)

        success = len(added) > 0 or len(skipped) == len(files)
        return {
            "success": success,
            "added": added,
            "skipped": skipped,
            "error": error,
        }

    def commit_and_push(self, message: str) -> Dict[str, Any]:
        """Commit local changes to tracked files and push to remote.

        Returns:
            Dictionary with result info:
            - success: Whether the operation completed successfully
            - committed: Whether a commit was made
            - pushed: Whether the push succeeded
            - error: Error message if any step failed
        """
        result = {
            "success": False,
            "committed": False,
            "pushed": False,
            "error": None,
        }

        # Resolve branch
        branch_info = self._resolve_branch()
        effective_branch = branch_info["effective"]

        if branch_info["reason"] == "not_found":
            result["error"] = branch_info["message"]
            return result

        # Get changed files
        changed = self._get_changed_files(branch=effective_branch)
        if not changed:
            result["success"] = True
            result["error"] = "No changes to commit"
            return result

        try:
            # Stage tracked files that have changes
            add_result = self._git("add", "-u", check=False)
            if add_result.returncode != 0:
                result["error"] = (
                    f"git add failed: {add_result.stderr.strip()}"
                )
                return result

            # Commit
            commit_result = self._git("commit", "-m", message, check=False)
            if commit_result.returncode != 0:
                if (
                    "nothing to commit" in commit_result.stdout
                    or "nothing to commit" in commit_result.stderr
                ):
                    result["success"] = True
                    result["error"] = "No changes to commit"
                    return result
                result["error"] = (
                    f"git commit failed: {commit_result.stderr.strip()}"
                )
                return result

            result["committed"] = True
            logger.info(f"Created commit on {effective_branch}")

        except subprocess.TimeoutExpired:
            result["error"] = "Commit timed out"
            return result
        except Exception as e:
            result["error"] = f"Commit failed: {e}"
            return result

        # Push
        try:
            push_result = self._git_bare(
                "push", "origin", effective_branch, check=False, timeout=60
            )
            if push_result.returncode == 0:
                result["pushed"] = True
                result["success"] = True
                logger.info(f"Pushed to origin/{effective_branch}")
            else:
                result["error"] = f"Push failed: {push_result.stderr.strip()}"
                logger.error(result["error"])
        except subprocess.TimeoutExpired:
            result["error"] = "Push timed out"
            logger.error(result["error"])
        except Exception as e:
            result["error"] = f"Push failed: {e}"
            logger.error(result["error"])

        return result

    def push(self) -> Dict[str, Any]:
        """Push local commits to remote.

        Returns:
            Dictionary with result info:
            - success: Whether push succeeded
            - error: Error message if failed
        """
        result = {"success": False, "error": None}

        branch_info = self._resolve_branch()
        effective_branch = branch_info["effective"]

        try:
            push_result = self._git_bare(
                "push",
                "-u",
                "origin",
                effective_branch,
                check=False,
                timeout=60,
            )
            if push_result.returncode == 0:
                result["success"] = True
                logger.info(f"Pushed to origin/{effective_branch}")
            else:
                result["error"] = push_result.stderr.strip()
                logger.error(f"Push failed: {result['error']}")
        except subprocess.TimeoutExpired:
            result["error"] = "Push timed out"
            logger.error(result["error"])
        except Exception as e:
            result["error"] = str(e)
            logger.error(f"Push failed: {e}")

        return result

    def force_checkout(self):
        """Discard local changes and update to match remote."""
        # Fetch first
        logger.info("Fetching latest from remote...")
        self._fetch()

        # Resolve branch
        branch_info = self._resolve_branch()
        effective_branch = branch_info["effective"]

        # Reset to remote
        try:
            self._git("reset", "--hard", f"origin/{effective_branch}")
            logger.info(f"Reset to origin/{effective_branch}")
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Reset failed: {e.stderr.strip()}")
