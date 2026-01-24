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
        """Main entry point for setting up dotfiles."""
        repo = self._get_repo()
        
        logger.info(f"Syncing dotfiles from origin...")
        repo.remotes.origin.fetch()
        
        # Ensure HEAD points to the correct branch
        repo.git.symbolic_ref("HEAD", f"refs/heads/{self.branch}")
        
        # We need to make sure the local branch exists and points to the remote one
        try:
            repo.git.update_ref(f"refs/heads/{self.branch}", f"origin/{self.branch}")
        except GitCommandError:
            pass

        # Configure status to ignore untracked files in $HOME
        with repo.config_writer() as writer:
            writer.set_value("status", "showUntrackedFiles", "no")
            writer.release()
        
        self._checkout_with_retry(repo)

    def _checkout_with_retry(self, repo: Repo, max_retries: int = 5):
        """Attempts checkout and handles conflicts by backing up files."""
        for attempt in range(max_retries):
            logger.info(f"Attempting checkout (attempt {attempt + 1})...")
            try:
                # Provide work tree only when needed
                repo.git.execute(["git", "--work-tree", str(self.work_tree), "checkout"])
                logger.info("Checkout successful!")
                return
            except GitCommandError as e:
                # Check if checkout failed due to existing files
                if "The following untracked working tree files would be overwritten by checkout" in e.stderr:
                    conflicting_files = self._parse_conflicting_files(e.stderr)
                    if not conflicting_files:
                        logger.error("Failed to parse conflicting files from git output.")
                        raise

                    self._backup_files(conflicting_files)
                else:
                    logger.error(f"Git checkout failed: {e.stderr}")
                    raise

        logger.error(f"Failed to checkout dotfiles after {max_retries} attempts.")
        raise RuntimeError("Dotfiles checkout failed.")

    def _parse_conflicting_files(self, git_output: str) -> List[str]:
        """Parses git error message to extract file paths."""
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
        """Moves conflicting files to a backup directory."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = self.work_tree / f".dotfiles_backup_{timestamp}"
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Backing up {len(file_paths)} conflicting files to {backup_dir}")
        
        for file_path in file_paths:
            src = self.work_tree / file_path
            dst = backup_dir / file_path
            
            if src.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                logger.debug(f"Moving {src} to {dst}")
                shutil.move(str(src), str(dst))
            else:
                logger.warning(f"Conflicting file {src} not found during backup.")

    def dotfiles_git(self, *args) -> str:
        """Helper to run arbitrary git commands on the dotfiles repo."""
        repo = self._get_repo()
        return repo.git.execute(list(args))

    def is_file_tracked(self, relative_path: str) -> bool:
        """Checks if a file is tracked in the dotfiles repository."""
        if not self.dotfiles_dir.exists():
            return False
        repo = self._get_repo()
        try:
            # Use ls-tree to check if the file exists in the current branch
            # We don't want the work tree here
            result = repo.git.ls_tree("-r", self.branch, relative_path, "--name-only")
            return len(result.strip()) > 0
        except GitCommandError:
            return False

    def get_status(self) -> dict:
        """Returns a status report of the dotfiles repository."""
        if not self.dotfiles_dir.exists():
            return {"installed": False}

        repo = self._get_repo()
        
        # Check remote changes
        logger.debug("Checking for remote updates...")
        repo.remotes.origin.fetch()
        
        # Check local changes
        # Provide work tree explicitly for status
        local_changes = repo.git.execute(["git", "--work-tree", str(self.work_tree), "status", "--porcelain"])
        
        local_commit = repo.head.commit.hexsha
        remote_commit = repo.refs[f"origin/{self.branch}"].commit.hexsha
        
        return {
            "installed": True,
            "local_changes": len(local_changes.strip()) > 0,
            "behind": local_commit != remote_commit,
            "local_commit": local_commit[:7],
            "remote_commit": remote_commit[:7]
        }

    def get_file_sync_status(self, relative_path: str) -> str:
        """
        Returns the sync status of a specific file:
        - 'up-to-date': Matches the remote branch.
        - 'modified'  : Has local changes relative to HEAD.
        - 'behind'    : Matches HEAD but is different from remote.
        - 'untracked' : Not in the repository.
        - 'missing'   : Tracked in repo but file doesn't exist in work tree.
        - 'not-found' : File doesn't exist locally AND is not tracked in repo.
        """
        if not self.dotfiles_dir.exists():
            return "not-initialized"

        repo = self._get_repo()
        local_file = self.work_tree / relative_path
        
        # 1. Check if tracked in HEAD or Remote
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

        # 2. Check local file
        if not local_file.exists():
            if is_tracked_head or is_tracked_remote:
                return "missing"
            else:
                return "not-found"

        # 3. File exists locally, check sync state
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
                # Tracked locally and no remote info or matches head
                return "up-to-date"
                
        except GitCommandError:
            return "error"
