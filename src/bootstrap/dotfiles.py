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
            # Bare repos often don't have this set by default
            with self._repo.config_writer() as writer:
                writer.set_value('remote "origin"', "fetch", "+refs/heads/*:refs/remotes/origin/*")
                writer.release()

            # Important: Tell the repo object where the work tree is
            self._repo.git.update_environment(GIT_WORK_TREE=str(self.work_tree))
        return self._repo

    def setup(self):
        """Main entry point for setting up dotfiles."""
        repo = self._get_repo()
        
        logger.info(f"Fetching updates from origin...")
        # Just fetch origin. This updates refs/remotes/origin/*
        repo.remotes.origin.fetch()
        
        # Ensure HEAD points to the correct branch
        repo.git.symbolic_ref("HEAD", f"refs/heads/{self.branch}")
        
        # We need to make sure the local branch exists and points to the remote one
        # If it's a fresh clone, we might need to create it.
        try:
            repo.git.update_ref(f"refs/heads/{self.branch}", f"origin/{self.branch}")
        except GitCommandError:
            # If origin branch doesn't exist, this might fail, but checkout will catch it
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
                repo.git.checkout()
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
