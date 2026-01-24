import shutil
import subprocess
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime
from git import Repo, GitCommandError

logger = logging.getLogger(__name__)


class DotfilesManager:
    def __init__(self, repo_url: str, dotfiles_dir: Path, work_tree: Path, branch: str = "main"):
        self.repo_url = repo_url
        self.dotfiles_dir = dotfiles_dir
        self.work_tree = work_tree
        self.branch = branch
        self._repo: Optional[Repo] = None

    def _git_cmd(self, *args: str) -> str:
        """Execute a git command with proper --git-dir and --work-tree flags.
        
        This ensures all commands consistently use the bare repo as git-dir
        and the user's home directory as work-tree.
        """
        repo = self._get_repo()
        cmd = [
            "git",
            f"--git-dir={self.dotfiles_dir}",
            f"--work-tree={self.work_tree}",
            *args
        ]
        return repo.git.execute(cmd)

    def _get_repo(self) -> Repo:
        """Initializes or returns the GitPython Repo object.
        
        Handles cloning if the repository doesn't exist yet.
        """
        if self._repo is None:
            if not self.dotfiles_dir.exists():
                logger.info(f"Cloning bare repository from {self.repo_url} to {self.dotfiles_dir}")
                self._repo = Repo.clone_from(self.repo_url, self.dotfiles_dir, bare=True)
                self._configure_repo(self._repo)
            else:
                self._repo = Repo(self.dotfiles_dir)
                self._configure_repo(self._repo)

        return self._repo

    def _configure_repo(self, repo: Repo):
        """Configure the repository with required settings."""
        with repo.config_writer() as writer:
            # Ensure proper fetch refspec for bare repo
            writer.set_value('remote "origin"', "fetch", "+refs/heads/*:refs/remotes/origin/*")
            # Don't show untracked files (the entire $HOME would show up otherwise)
            writer.set_value("status", "showUntrackedFiles", "no")
            writer.release()

    def _setup_branch(self, repo: Repo):
        """Set up the local branch to track the remote branch.
        
        After cloning a bare repo, HEAD may not point to a valid branch.
        We need to fetch and set up the branch properly before checkout.
        """
        # Fetch to ensure we have the remote refs
        logger.debug("Fetching remote refs...")
        repo.remotes.origin.fetch()
        
        # Set HEAD to point to the target branch
        try:
            repo.git.symbolic_ref("HEAD", f"refs/heads/{self.branch}")
        except GitCommandError as e:
            logger.debug(f"Could not set symbolic ref: {e}")
        
        # Update the local branch ref to point to the remote branch
        try:
            repo.git.update_ref(f"refs/heads/{self.branch}", f"origin/{self.branch}")
        except GitCommandError as e:
            logger.debug(f"Could not update ref: {e}")

    def setup(self):
        """Initial setup: clone repo and checkout dotfiles to home directory."""
        if not self.dotfiles_dir.exists():
            # _get_repo() handles cloning if directory doesn't exist
            repo = self._get_repo()
            self._setup_branch(repo)
            self._checkout_with_retry(repo)

    def _checkout_with_retry(self, repo: Repo, max_retries: int = 5):
        """Attempts checkout and handles conflicts by backing up files.
        
        Note: This parses git error messages to detect conflicting files.
        This is fragile and may break if git changes its output format,
        but there's no better programmatic way to get this information.
        """
        for attempt in range(max_retries):
            logger.info(f"Attempting checkout (attempt {attempt + 1})...")
            try:
                self._git_cmd("checkout")
                logger.info("Checkout successful!")
                return
            except GitCommandError as e:
                if "The following untracked working tree files would be overwritten by checkout" in e.stderr:
                    conflicting_files = self._parse_conflicting_files(e.stderr)
                    if not conflicting_files:
                        raise
                    self._backup_files(conflicting_files)
                else:
                    raise
        raise RuntimeError("Dotfiles checkout failed after max retries.")

    def _parse_conflicting_files(self, git_output: str) -> List[str]:
        """Parse git error output to extract conflicting file paths.
        
        WARNING: This relies on parsing git's human-readable error messages,
        which is inherently fragile. Git may change its output format between
        versions. Unfortunately, there's no --porcelain equivalent for this error.
        """
        files = []
        capture = False
        for line in git_output.splitlines():
            line = line.strip()
            if "The following untracked working tree files would be overwritten by checkout" in line:
                capture = True
                continue
            if "Please move or remove them before you switch branches" in line:
                capture = False
                continue
            if capture and line:
                files.append(line)
        return files

    def _backup_files(self, file_paths: List[str]):
        """Move conflicting files to a timestamped backup directory."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = self.work_tree / f".dotfiles_backup_{timestamp}"
        backup_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Backing up {len(file_paths)} conflicting files to {backup_dir}")
        for file_path in file_paths:
            src = self.work_tree / file_path
            dst = backup_dir / file_path
            if src.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst))

    def _fetch_with_fallback(self, repo: Repo) -> bool:
        """Attempt to fetch from remote, returning False if network unavailable."""
        try:
            repo.remotes.origin.fetch()
            return True
        except GitCommandError as e:
            logger.warning(f"Could not fetch from remote (offline?): {e}")
            return False

    def get_detailed_status(self, offline: bool = False) -> Dict[str, Any]:
        """Get detailed sync status of the dotfiles repository.
        
        Args:
            offline: If True, skip fetching from remote (use cached state).
            
        Returns:
            Dictionary with sync status information including:
            - initialized: Whether the repo exists
            - has_local_changes: Whether there are uncommitted local changes
            - changed_files: List of changed file paths
            - is_ahead: Whether local has commits not on remote
            - is_behind: Whether remote has commits not on local
            - local_commit: Short hash of local HEAD
            - remote_commit: Short hash of remote branch tip
            - fetch_failed: Whether the fetch attempt failed (network issues)
        """
        if not self.dotfiles_dir.exists():
            return {"initialized": False}
        
        repo = self._get_repo()
        
        fetch_failed = False
        if not offline:
            fetch_failed = not self._fetch_with_fallback(repo)
        
        # Get porcelain status to see which files changed
        status_output = self._git_cmd("status", "--porcelain")
        changed_files = []
        for line in status_output.splitlines():
            if line.strip():
                # Porcelain format is 'XY path' where XY is 2 chars
                changed_files.append(line[3:])
        
        local_commit = repo.head.commit.hexsha
        
        # Handle case where remote branch might not exist yet
        try:
            remote_commit = repo.refs[f"origin/{self.branch}"].commit.hexsha
        except (IndexError, KeyError):
            # Remote branch not found - likely a new repo or fetch failed
            return {
                "initialized": True,
                "has_local_changes": len(changed_files) > 0,
                "changed_files": changed_files,
                "is_ahead": False,
                "is_behind": False,
                "local_commit": local_commit[:7],
                "remote_commit": None,
                "fetch_failed": fetch_failed,
            }
        
        # Proper ahead/behind detection
        try:
            behind_count = int(repo.git.rev_list("--count", f"HEAD..origin/{self.branch}"))
            ahead_count = int(repo.git.rev_list("--count", f"origin/{self.branch}..HEAD"))
        except GitCommandError:
            behind_count = 0
            ahead_count = 0
        
        return {
            "initialized": True,
            "has_local_changes": len(changed_files) > 0,
            "changed_files": changed_files,
            "is_ahead": ahead_count > 0,
            "is_behind": behind_count > 0,
            "ahead_count": ahead_count,
            "behind_count": behind_count,
            "local_commit": local_commit[:7],
            "remote_commit": remote_commit[:7],
            "fetch_failed": fetch_failed,
        }

    def get_file_sync_status(self, relative_path: str) -> str:
        """Get sync status of a specific file.
        
        Returns one of:
        - 'not-initialized': Repo doesn't exist
        - 'not-found': File doesn't exist locally and isn't tracked
        - 'missing': File is tracked but doesn't exist locally
        - 'untracked': File exists locally but isn't tracked
        - 'up-to-date': File matches remote
        - 'modified': File has local changes
        - 'behind': File is outdated (remote has newer version)
        - 'error': Could not determine status
        """
        if not self.dotfiles_dir.exists():
            return "not-initialized"
        
        repo = self._get_repo()
        local_file = self.work_tree / relative_path
        
        # Check if tracked in HEAD
        is_tracked_head = False
        head_sha = None
        try:
            head_sha = repo.git.rev_parse(f"HEAD:{relative_path}")
            is_tracked_head = True
        except GitCommandError:
            pass
        
        # Check if tracked in remote
        is_tracked_remote = False
        remote_sha = None
        try:
            remote_sha = repo.git.rev_parse(f"origin/{self.branch}:{relative_path}")
            is_tracked_remote = True
        except GitCommandError:
            pass
        
        if not local_file.exists():
            return "missing" if (is_tracked_head or is_tracked_remote) else "not-found"
        
        try:
            local_sha = repo.git.hash_object(str(local_file))
            
            if not is_tracked_head:
                return "untracked"
            if remote_sha and local_sha == remote_sha:
                return "up-to-date"
            elif local_sha != head_sha:
                return "modified"
            elif remote_sha and head_sha != remote_sha:
                return "behind"
            else:
                return "up-to-date"
        except GitCommandError:
            return "error"

    def commit_and_push(self, message: str) -> Dict[str, Any]:
        """Commits and pushes changes to already-tracked dotfiles only.
        
        Uses 'git add -u' to stage only modifications to files that are 
        already tracked in the repository, preventing accidental inclusion
        of untracked files from the home directory.
        
        Returns:
            Dictionary with result info:
            - success: Whether the operation completed successfully
            - committed: Whether a commit was made
            - pushed: Whether the push succeeded
            - error: Error message if any step failed
        """
        repo = self._get_repo()
        result = {"success": False, "committed": False, "pushed": False, "error": None}
        
        try:
            # Stage only tracked files (NEVER use -A with $HOME as work tree!)
            self._git_cmd("add", "-u")
            
            # Check if there are staged changes
            staged = self._git_cmd("diff", "--cached", "--quiet")
        except GitCommandError:
            # diff --quiet returns non-zero if there are differences (i.e., staged changes)
            pass
        
        # Check if there's anything to commit
        try:
            # This will fail if nothing to commit
            self._git_cmd("diff", "--cached", "--exit-code")
            # If we get here, there are no staged changes
            logger.info("No changes to commit")
            result["success"] = True
            result["error"] = "No changes to commit"
            return result
        except GitCommandError:
            # There are staged changes, proceed with commit
            pass
        
        try:
            logger.info(f"Committing changes: {message}")
            self._git_cmd("commit", "-m", message)
            result["committed"] = True
        except GitCommandError as e:
            result["error"] = f"Commit failed: {e}"
            return result
        
        try:
            logger.info(f"Pushing to origin/{self.branch}")
            repo.remotes.origin.push(self.branch)
            result["pushed"] = True
            result["success"] = True
        except GitCommandError as e:
            result["error"] = f"Push failed (changes committed locally): {e}"
            logger.error(result["error"])
            # Commit succeeded but push failed - inform user
        
        return result

    def force_checkout(self):
        """Discard local changes and update to match remote.
        
        Fetches latest from remote, resets HEAD to remote branch,
        and force-checkouts files to work tree.
        """
        repo = self._get_repo()
        
        # Fetch first to ensure we have latest remote state
        logger.info("Fetching latest from remote...")
        repo.remotes.origin.fetch()
        
        logger.info("Discarding local changes and updating to remote...")
        self._git_cmd("reset", "--hard", f"origin/{self.branch}")
        self._git_cmd("checkout", "-f")
