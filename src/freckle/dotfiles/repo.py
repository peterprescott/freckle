"""Low-level git operations for bare repositories."""

import logging
import subprocess
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


class BareGitRepo:
    """Low-level git operations for a bare repository with work tree.

    Provides a clean abstraction over git subprocess calls,
    handling the --git-dir and --work-tree flags automatically.
    """

    def __init__(self, git_dir: Path, work_tree: Path):
        """Initialize the bare git repo wrapper.

        Args:
            git_dir: Path to the bare git repository
            work_tree: Path to the work tree (e.g., home directory)
        """
        self.git_dir = Path(git_dir)
        self.work_tree = Path(work_tree)

    def run(
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
            str(self.git_dir),
            "--work-tree",
            str(self.work_tree),
        ] + list(args)
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=check,
            cwd=str(self.work_tree),
        )

    def run_bare(
        self, *args, check: bool = True, timeout: int = 60
    ) -> subprocess.CompletedProcess:
        """Run a git command with just --git-dir (no work tree).

        Used for operations that don't need a work tree context.
        """
        cmd = ["git", "--git-dir", str(self.git_dir)] + list(args)
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=check
        )

    def clone_bare(self, repo_url: str, timeout: int = 120):
        """Clone a repository as a bare repo."""
        logger.info(
            f"Cloning bare repo from {repo_url} to {self.git_dir}"
        )
        subprocess.run(
            ["git", "clone", "--bare", repo_url, str(self.git_dir)],
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def init_bare(self, initial_branch: str = "main"):
        """Initialize a new bare repository."""
        logger.info(f"Creating new bare repository at {self.git_dir}")
        subprocess.run(
            [
                "git",
                "init",
                "--bare",
                f"--initial-branch={initial_branch}",
                str(self.git_dir),
            ],
            check=True,
            capture_output=True,
            text=True,
        )

    def ensure_fetch_refspec(self):
        """Ensure fetch refspec is configured for remote tracking.

        Bare repos created manually often lack the fetch refspec,
        which prevents remote-tracking branches from being created.
        """
        try:
            result = self.run_bare(
                "config", "--get-all", "remote.origin.fetch", check=False
            )
            expected = "+refs/heads/*:refs/remotes/origin/*"

            if expected not in result.stdout:
                logger.info("Configuring fetch refspec for remote tracking")
                self.run_bare(
                    "config", "--add", "remote.origin.fetch", expected
                )
        except Exception as e:
            logger.debug(f"Could not configure fetch refspec: {e}")

    def fetch(self, timeout: int = 60) -> bool:
        """Fetch from remote origin. Returns True on success."""
        self.ensure_fetch_refspec()

        try:
            self.run_bare("fetch", "origin", timeout=timeout)
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

    def get_available_branches(self) -> List[str]:
        """Get list of all available branch names (local and remote)."""
        branches = set()

        try:
            # Get local branches
            result = self.run_bare(
                "for-each-ref",
                "--format=%(refname:short)",
                "refs/heads/",
                check=False,
            )
            for line in result.stdout.strip().split("\n"):
                if line.strip():
                    branches.add(line.strip())

            # Get remote branches
            result = self.run_bare(
                "for-each-ref",
                "--format=%(refname:short)",
                "refs/remotes/origin/",
                check=False,
            )
            for line in result.stdout.strip().split("\n"):
                if line.strip() and not line.strip().endswith("/HEAD"):
                    branch = line.strip()
                    if branch.startswith("origin/"):
                        branch = branch[7:]
                    branches.add(branch)
        except Exception as e:
            logger.debug(f"Could not get branches: {e}")

        return sorted(branches)

    def get_head_branch(self) -> Optional[str]:
        """Get the current HEAD branch name."""
        try:
            result = self.run_bare(
                "symbolic-ref", "--short", "HEAD", check=False
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return None

    def get_commit_info(self, ref: str) -> Optional[str]:
        """Get short commit hash for a ref, or None if it doesn't exist."""
        try:
            result = self.run_bare("rev-parse", "--short", ref, check=False)
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return None

    def get_ahead_behind(self, local_ref: str, remote_ref: str) -> tuple:
        """Get ahead/behind counts between two refs."""
        try:
            result = self.run_bare(
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

    def branch_exists(self, branch: str) -> bool:
        """Check if a branch exists locally or on remote."""
        try:
            # Check local
            result = self.run_bare(
                "show-ref", "--verify", f"refs/heads/{branch}", check=False
            )
            if result.returncode == 0:
                return True

            # Check remote
            result = self.run_bare(
                "show-ref",
                "--verify",
                f"refs/remotes/origin/{branch}",
                check=False,
            )
            return result.returncode == 0
        except Exception:
            return False

    def get_tracked_files(self, branch: str) -> List[str]:
        """Get list of all files tracked in the specified branch."""
        try:
            for ref in [f"origin/{branch}", branch]:
                result = self.run_bare(
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

    def get_changed_files(self) -> List[str]:
        """Get list of files that differ between work tree and HEAD."""
        try:
            result = self.run("diff", "--name-only", "HEAD", check=False)
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

    def setup_branch(self, branch: str):
        """Set up the local branch to track remote after cloning."""
        try:
            self.fetch()

            # Check if remote branch exists
            result = self.run_bare(
                "show-ref",
                "--verify",
                f"refs/remotes/origin/{branch}",
                check=False,
            )
            if result.returncode != 0:
                logger.warning(f"Remote branch origin/{branch} not found")
                return

            # Create local branch tracking remote
            self.run_bare(
                "branch", "-f", branch, f"origin/{branch}", check=False
            )

            # Set HEAD to the branch
            self.run_bare("symbolic-ref", "HEAD", f"refs/heads/{branch}")
        except Exception as e:
            logger.warning(f"Could not set up branch: {e}")
