"""Shared helpers for profile commands."""

import subprocess
from typing import Optional

from ..helpers import get_config, get_dotfiles_dir, get_dotfiles_manager


def get_current_branch() -> Optional[str]:
    """Get the current git branch for dotfiles."""
    config = get_config()
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
