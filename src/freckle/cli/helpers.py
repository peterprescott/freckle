"""Shared helper functions for CLI commands."""

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from ..config import Config
from ..dotfiles import DotfilesManager
from ..system import Environment

# Global environment instance
env = Environment()
logger = logging.getLogger(__name__)

# Canonical config path
CONFIG_FILENAME = ".freckle.yaml"
CONFIG_PATH = env.home / CONFIG_FILENAME


def get_config() -> Config:
    """Load config from ~/.freckle.yaml."""
    return Config(CONFIG_PATH, env=env)


def get_dotfiles_manager(config: Config) -> Optional[DotfilesManager]:
    """Create a DotfilesManager from config."""
    repo_url = config.get("dotfiles.repo_url")
    if not repo_url:
        return None

    dotfiles_dir = Path(config.get("dotfiles.dir")).expanduser()
    if not dotfiles_dir.is_absolute():
        dotfiles_dir = env.home / dotfiles_dir
    branch = config.get_branch()

    return DotfilesManager(repo_url, dotfiles_dir, env.home, branch)


def get_dotfiles_dir(config: Config) -> Path:
    """Get the dotfiles directory path from config."""
    dotfiles_dir = Path(config.get("dotfiles.dir")).expanduser()
    if not dotfiles_dir.is_absolute():
        dotfiles_dir = env.home / dotfiles_dir
    return dotfiles_dir


def get_subprocess_error(e: subprocess.CalledProcessError) -> str:
    """Extract error message from CalledProcessError.

    Handles both string and bytes stderr, returning a clean string.
    """
    stderr = getattr(e, "stderr", "")
    if isinstance(stderr, bytes):
        stderr = stderr.decode("utf-8", errors="replace")
    return stderr.strip()


def is_git_available() -> bool:
    """Check if git is installed and accessible."""
    return shutil.which("git") is not None
