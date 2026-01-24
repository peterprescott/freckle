import subprocess
import shutil
import logging
from pathlib import Path
from typing import List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class DotfilesManager:
    def __init__(self, repo_url: str, dotfiles_dir: Path, work_tree: Path, branch: str = "master"):
        self.repo_url = repo_url
        self.dotfiles_dir = dotfiles_dir
        self.work_tree = work_tree
        self.branch = branch
        self.git_cmd = ["git", "--git-dir", str(self.dotfiles_dir), "--work-tree", str(self.work_tree)]

    def setup(self):
        """Main entry point for setting up dotfiles."""
        if not self.dotfiles_dir.exists():
            self._clone_bare()
        else:
            self._fetch_updates()
        
        # Ensure HEAD points to the correct branch
        subprocess.run(
            self.git_cmd + ["symbolic-ref", "HEAD", f"refs/heads/{self.branch}"],
            check=True
        )
        
        self._configure_status()
        self._checkout_with_retry()

    def _clone_bare(self):
        logger.info(f"Cloning bare repository from {self.repo_url} to {self.dotfiles_dir}")
        subprocess.run(
            ["git", "clone", "--bare", self.repo_url, str(self.dotfiles_dir)],
            check=True
        )

    def _fetch_updates(self):
        logger.info(f"Fetching updates from remote branch: {self.branch}")
        subprocess.run(
            self.git_cmd + ["fetch", "origin", f"{self.branch}:{self.branch}"],
            check=False # Might fail if branch doesn't exist yet locally, which is fine
        )
        subprocess.run(
            self.git_cmd + ["fetch", "origin", self.branch],
            check=True
        )

    def _configure_status(self):
        """Configures the repo to not show untracked files in the work tree (HOME)."""
        subprocess.run(
            self.git_cmd + ["config", "--local", "status.showUntrackedFiles", "no"],
            check=True
        )

    def _checkout_with_retry(self, max_retries: int = 5):
        """Attempts checkout and handles conflicts by backing up files."""
        for attempt in range(max_retries):
            logger.info(f"Attempting checkout (attempt {attempt + 1})...")
            result = subprocess.run(
                self.git_cmd + ["checkout"],
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                logger.info("Checkout successful!")
                return

            # Check if checkout failed due to existing files
            if "The following untracked working tree files would be overwritten by checkout" in result.stderr:
                conflicting_files = self._parse_conflicting_files(result.stderr)
                if not conflicting_files:
                    logger.error("Failed to parse conflicting files from git output.")
                    result.check_returncode()

                self._backup_files(conflicting_files)
            else:
                # Some other error occurred
                logger.error(f"Git checkout failed: {result.stderr}")
                result.check_returncode()

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
                # Git output usually prefixes with tab or spaces
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

    def dotfiles_git(self, *args) -> subprocess.CompletedProcess:
        """Helper to run arbitrary git commands on the dotfiles repo."""
        return subprocess.run(
            self.git_cmd + list(args),
            capture_output=True,
            text=True
        )
