"""Git history operations for dotfiles repository."""

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class CommitInfo:
    """Information about a git commit."""

    hash: str
    date: str
    date_raw: str
    author: str
    subject: str
    files: List[str]


class GitHistoryService:
    """Service for git history operations on a bare dotfiles repo.

    Centralizes all git history/diff operations to avoid code duplication
    across CLI modules.
    """

    def __init__(self, git_dir: Path, work_tree: Path):
        """Initialize with git directory and work tree paths.

        Args:
            git_dir: Path to the bare git repository
            work_tree: Path to the working directory (typically home)
        """
        self.git_dir = git_dir
        self.work_tree = work_tree

    def _run_git(
        self,
        *args: str,
        timeout: int = 30,
        check: bool = False,
    ) -> subprocess.CompletedProcess:
        """Run a git command with the correct paths.

        Args:
            *args: Git command arguments
            timeout: Command timeout in seconds
            check: Whether to raise on non-zero exit

        Returns:
            CompletedProcess result
        """
        cmd = [
            "git",
            "--git-dir",
            str(self.git_dir),
            "--work-tree",
            str(self.work_tree),
            *args,
        ]
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=check,
        )

    def is_valid_commit(self, ref: str) -> bool:
        """Check if a commit reference is valid.

        Args:
            ref: Commit hash or reference

        Returns:
            True if the reference is a valid commit
        """
        try:
            result = self._run_git(
                "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, Exception):
            return False

    def get_commit_subject(self, ref: str) -> Optional[str]:
        """Get the subject line of a commit.

        Args:
            ref: Commit hash or reference

        Returns:
            Commit subject line, or None if not found
        """
        try:
            result = self._run_git(
                "log",
                "-1",
                "--format=%s",
                ref,
                timeout=10,
            )
            if result.returncode == 0:
                return result.stdout.strip()
            return None
        except (subprocess.TimeoutExpired, Exception):
            return None

    def get_file_at_commit(self, ref: str, path: str) -> Optional[str]:
        """Get file contents at a specific commit.

        Args:
            ref: Commit hash or reference
            path: Repo-relative file path

        Returns:
            File contents as string, or None if not found
        """
        try:
            result = self._run_git(
                "show",
                f"{ref}:{path}",
                timeout=10,
            )
            if result.returncode == 0:
                return result.stdout
            return None
        except (subprocess.TimeoutExpired, Exception):
            return None

    def get_commit_files(
        self,
        ref: str,
        filter_paths: Optional[List[str]] = None,
    ) -> List[str]:
        """Get list of files changed in a commit.

        Args:
            ref: Commit hash or reference
            filter_paths: Optional list of paths to filter by

        Returns:
            List of changed file paths
        """
        try:
            result = self._run_git(
                "diff-tree",
                "--no-commit-id",
                "--name-only",
                "-r",
                ref,
                timeout=10,
            )
            if result.returncode != 0:
                return []

            files = [
                f.strip()
                for f in result.stdout.strip().split("\n")
                if f.strip()
            ]

            if filter_paths:
                filtered = []
                for f in files:
                    for filter_path in filter_paths:
                        if f == filter_path or f.startswith(
                            filter_path.rstrip("/") + "/"
                        ):
                            filtered.append(f)
                            break
                return filtered

            return files
        except Exception:
            return []

    def get_file_history(
        self,
        file_paths: List[str],
        limit: int = 20,
    ) -> List[CommitInfo]:
        """Get commit history for specific files.

        Args:
            file_paths: List of repo-relative file paths
            limit: Maximum number of commits

        Returns:
            List of CommitInfo objects
        """
        try:
            format_str = "%h|%aI|%an|%s"
            result = self._run_git(
                "log",
                f"--format={format_str}",
                f"-n{limit}",
                "--follow",
                "--",
                *file_paths,
            )

            if result.returncode != 0:
                return []

            commits = []
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue

                parts = line.split("|", 3)
                if len(parts) < 4:
                    continue

                commit_hash, date_str, author, subject = parts
                files = self.get_commit_files(commit_hash, file_paths)

                commits.append(
                    CommitInfo(
                        hash=commit_hash,
                        date=date_str,  # Will be formatted by caller
                        date_raw=date_str,
                        author=author,
                        subject=subject,
                        files=files,
                    )
                )

            return commits
        except Exception:
            return []

    def get_general_history(
        self,
        limit: int = 20,
        oneline: bool = False,
    ) -> List[CommitInfo]:
        """Get general commit history for the repo.

        Args:
            limit: Maximum number of commits
            oneline: Whether to skip file listing

        Returns:
            List of CommitInfo objects
        """
        try:
            format_str = "%h|%aI|%an|%s"
            result = self._run_git(
                "log",
                f"--format={format_str}",
                f"-n{limit}",
            )

            if result.returncode != 0:
                return []

            commits = []
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue

                parts = line.split("|", 3)
                if len(parts) < 4:
                    continue

                commit_hash, date_str, author, subject = parts
                files = [] if oneline else self.get_commit_files(commit_hash)

                commits.append(
                    CommitInfo(
                        hash=commit_hash,
                        date=date_str,
                        date_raw=date_str,
                        author=author,
                        subject=subject,
                        files=files,
                    )
                )

            return commits
        except Exception:
            return []

    def get_diff(
        self,
        ref1: str,
        ref2: str,
        paths: Optional[List[str]] = None,
    ) -> str:
        """Get diff between two commits.

        Args:
            ref1: First commit reference
            ref2: Second commit reference
            paths: Optional list of paths to filter

        Returns:
            Diff output as string
        """
        try:
            cmd_args = ["diff", ref1, ref2]
            if paths:
                cmd_args.extend(["--", *paths])

            result = self._run_git(*cmd_args)
            return result.stdout if result.returncode == 0 else ""
        except Exception:
            return ""

    def get_diff_preview(
        self,
        ref: str,
        paths: Optional[List[str]] = None,
        max_lines: int = 4,
    ) -> str:
        """Get a compact diff preview for a commit.

        Args:
            ref: Commit reference
            paths: Optional list of paths to filter
            max_lines: Maximum number of diff lines to return

        Returns:
            Compact diff preview string
        """
        try:
            cmd_args = [
                "show",
                ref,
                "--format=",
                "--stat",
                f"-n{max_lines}",
            ]
            if paths:
                cmd_args.extend(["--", *paths])

            result = self._run_git(*cmd_args, timeout=10)
            if result.returncode == 0:
                lines = result.stdout.strip().split("\n")
                return "\n".join(lines[:max_lines])
            return ""
        except Exception:
            return ""
