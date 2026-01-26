"""Shared helpers for profile commands."""

import subprocess
from typing import TYPE_CHECKING, Optional

from ..helpers import get_config, get_dotfiles_dir, get_dotfiles_manager

if TYPE_CHECKING:
    from freckle.config import Config
    from freckle.dotfiles import DotfilesManager


def get_current_branch(
    config: Optional["Config"] = None,
    dotfiles: Optional["DotfilesManager"] = None,
) -> Optional[str]:
    """Get the current git branch for dotfiles.

    Args:
        config: Optional config object (avoids re-loading if provided)
        dotfiles: Optional dotfiles manager (avoids re-creating if provided)

    Returns:
        Current branch name, or None if not available
    """
    if config is None:
        config = get_config()

    if dotfiles is None:
        dotfiles = get_dotfiles_manager(config)

    if not dotfiles:
        return None

    dotfiles_dir = get_dotfiles_dir(config)
    if not dotfiles_dir.exists():
        return None

    try:
        result = dotfiles._git.run("rev-parse", "--abbrev-ref", "HEAD")
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None
