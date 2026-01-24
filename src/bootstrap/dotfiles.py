import shutil
import logging
import git
from pathlib import Path
from typing import List, Optional
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

    def _get_repo(self) -> Repo:
        """Initializes or returns the GitPython Repo object."""
        if self._repo is None:
            if not self.dotfiles_dir.exists():
                logger.info(f"Cloning bare repository from {self.repo_url} to {self.dotfiles_dir}")
                self._repo = Repo.clone_from(self.repo_url, self.dotfiles_dir, bare=True)
            else:
                self._repo = Repo(self.dotfiles_dir)
            
            # Ensure the remote 'origin' has the correct fetch refspec
            with self._repo.config_writer() as writer:
                writer.set_value('remote "origin"', "fetch", "+refs/heads/*:refs/remotes/origin/*")
                writer.release()

        return self._repo

    def setup(self):
        """Initial setup logic."""
        if not self.dotfiles_dir.exists():
            self._clone_bare()
            self._configure_status()
            self._checkout_with_retry(self._get_repo())

    def _clone_bare(self):
        logger.info(f"Cloning bare repository from {self.repo_url} to {self.dotfiles_dir}")
        subprocess_cmd = ["git", "clone", "--bare", self.repo_url, str(self.dotfiles_dir)]
        import subprocess
        subprocess.run(subprocess_cmd, check=True)

    def _configure_status(self):
        """Configures the repo to not show untracked files in the work tree (HOME)."""
        repo = self._get_repo()
        with repo.config_writer() as writer:
            writer.set_value("status", "showUntrackedFiles", "no")
            writer.release()

    def _checkout_with_retry(self, repo: Repo, max_retries: int = 5):
        """Attempts checkout and handles conflicts by backing up files."""
        for attempt in range(max_retries):
            logger.info(f"Attempting checkout (attempt {attempt + 1})...")
            try:
                repo.git.execute(["git", "--work-tree", str(self.work_tree), "checkout"])
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

    def get_detailed_status(self) -> dict:
        if not self.dotfiles_dir.exists():
            return {"initialized": False}
        repo = self._get_repo()
        logger.debug("Checking for remote updates...")
        repo.remotes.origin.fetch()
        
        # Get porcelain status to see which files changed
        status_output = repo.git.execute(["git", "--work-tree", str(self.work_tree), "status", "--porcelain"])
        changed_files = []
        for line in status_output.splitlines():
            if line.strip():
                # Porcelain format is 'XY path'
                changed_files.append(line[3:])
        
        local_commit = repo.head.commit.hexsha
        remote_commit = repo.refs[f"origin/{self.branch}"].commit.hexsha
        
        return {
            "initialized": True,
            "has_local_changes": len(changed_files) > 0,
            "changed_files": changed_files,
            "has_remote_changes": local_commit != remote_commit,
            "local_commit": local_commit[:7],
            "remote_commit": remote_commit[:7]
        }

    def get_file_sync_status(self, relative_path: str) -> str:
        if not self.dotfiles_dir.exists():
            return "not-initialized"
        repo = self._get_repo()
        local_file = self.work_tree / relative_path
        is_tracked_head = False
        try:
            head_sha = repo.git.rev_parse(f"HEAD:{relative_path}")
            is_tracked_head = True
        except GitCommandError:
            head_sha = None
        is_tracked_remote = False
        try:
            remote_sha = repo.git.rev_parse(f"origin/{self.branch}:{relative_path}")
            is_tracked_remote = True
        except GitCommandError:
            remote_sha = None
        if not local_file.exists():
            return "missing" if (is_tracked_head or is_tracked_remote) else "not-found"
        try:
            local_sha = repo.git.hash_object(str(local_file))
            if not is_tracked_head: return "untracked"
            if remote_sha and local_sha == remote_sha: return "up-to-date"
            elif local_sha != head_sha: return "modified"
            elif remote_sha and head_sha != remote_sha: return "behind"
            else: return "up-to-date"
        except GitCommandError: return "error"

    def commit_and_push(self, message: str):
        repo = self._get_repo()
        logger.info(f"Backing up local changes: {message}")
        repo.git.execute(["git", "--work-tree", str(self.work_tree), "add", "-A"])
        repo.git.execute(["git", "--work-tree", str(self.work_tree), "commit", "-m", message])
        repo.remotes.origin.push(self.branch)

    def force_checkout(self):
        repo = self._get_repo()
        logger.info("Discarding local changes and updating to remote...")
        repo.git.execute(["git", "reset", "--hard", f"origin/{self.branch}"])
        repo.git.execute(["git", "--work-tree", str(self.work_tree), "checkout", "-f"])
