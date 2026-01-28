"""Shared helper functions for CLI commands."""

import logging
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

import typer

from ..config import Config
from ..dotfiles import DotfilesManager
from ..system import Environment

# Global environment instance
env = Environment()
logger = logging.getLogger(__name__)

# Supported config filenames (in order of preference)
CONFIG_FILENAMES: List[str] = [".freckle.yaml", ".freckle.yml"]


def get_config_path(home: Optional[Path] = None) -> Path:
    """Find the config file path, checking both .yaml and .yml extensions.

    Returns the first existing config file, or the default (.freckle.yaml)
    if none exist yet.
    """
    home_dir = home or env.home
    for filename in CONFIG_FILENAMES:
        path = home_dir / filename
        if path.exists():
            return path
    # Default to .freckle.yaml if none exist
    return home_dir / CONFIG_FILENAMES[0]


# For backward compatibility
CONFIG_FILENAME = CONFIG_FILENAMES[0]
CONFIG_PATH = get_config_path()


def get_config() -> Config:
    """Load config from ~/.freckle.yaml or ~/.freckle.yml."""
    return Config(get_config_path(), env=env)


def get_dotfiles_manager(config: Config) -> Optional[DotfilesManager]:
    """Create a DotfilesManager from config."""
    repo_url = config.get("dotfiles.repo_url")
    if not repo_url:
        return None

    dotfiles_dir = Path(config.get("dotfiles.dir")).expanduser()
    if not dotfiles_dir.is_absolute():
        dotfiles_dir = env.home / dotfiles_dir

    # Try to get actual git branch, fall back to configured default
    branch = config.get_default_branch()
    if dotfiles_dir.exists():
        try:
            from ..dotfiles import BareGitRepo
            git = BareGitRepo(dotfiles_dir, env.home)
            result = git.run("rev-parse", "--abbrev-ref", "HEAD")
            actual_branch = result.stdout.strip()
            if actual_branch:
                branch = actual_branch
        except Exception:
            pass  # Fall back to configured branch

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


def require_dotfiles_ready(
    config: Config,
) -> Tuple[DotfilesManager, Path]:
    """Ensure dotfiles are configured and initialized.

    Call this at the start of commands that require a working dotfiles
    repository. Raises typer.Exit(1) with a helpful message if dotfiles
    are not configured or the repository doesn't exist.

    Args:
        config: The loaded freckle config.

    Returns:
        Tuple of (DotfilesManager, dotfiles_dir Path).

    Raises:
        typer.Exit(1): If dotfiles not configured or repo not found.
    """
    from .output import error

    dotfiles = get_dotfiles_manager(config)
    if not dotfiles:
        error("Dotfiles not configured. Run 'freckle init' first.")
        raise typer.Exit(1)

    dotfiles_dir = get_dotfiles_dir(config)
    if not dotfiles_dir.exists():
        error("Dotfiles repository not found. Run 'freckle init' first.")
        raise typer.Exit(1)

    return dotfiles, dotfiles_dir


def get_secret_scanner(config: Config):
    """Create a SecretScanner configured from the freckle config.

    Args:
        config: The freckle config object.

    Returns:
        A SecretScanner configured with any custom block/allow patterns.
    """
    from ..secrets import SecretScanner

    secrets_config = config.get("secrets", {})
    return SecretScanner(
        extra_block=secrets_config.get("block", []),
        extra_allow=secrets_config.get("allow", []),
    )


def normalize_to_home_relative(
    path_str: str,
    prefer_existing: bool = True,
    home: Optional[Path] = None,
) -> Optional[str]:
    """Convert a path string to a home-relative path.

    Handles various path formats:
    - ~/file -> file
    - /absolute/path -> path (if under home)
    - ./relative/file -> relative/file (resolved from cwd)
    - relative/file -> relative/file (resolved from cwd or home)

    Args:
        path_str: The path string to normalize (can be absolute, relative,
            or tilde-prefixed)
        prefer_existing: If True and path is relative, check cwd first,
            then home. If False, always resolve relative to cwd.
        home: Home directory to use. Defaults to env.home.

    Returns:
        Home-relative path string, or None if path is outside home directory.
    """
    home_dir = home or env.home
    path = Path(path_str).expanduser()

    if not path.is_absolute():
        if prefer_existing:
            # Try cwd first, then home
            cwd_path = Path.cwd() / path
            home_path = home_dir / path

            if cwd_path.exists():
                path = cwd_path.resolve()
            elif home_path.exists():
                path = home_path.resolve()
            else:
                # Default to home if neither exists
                path = home_path.resolve()
        else:
            # Always resolve from cwd
            path = (Path.cwd() / path).resolve()

    try:
        return str(path.relative_to(home_dir))
    except ValueError:
        return None
