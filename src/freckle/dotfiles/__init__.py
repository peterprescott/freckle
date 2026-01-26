"""Dotfiles management package."""

from .branch import BranchResolver
from .git import BareGitRepo
from .manager import DotfilesManager

__all__ = [
    "BareGitRepo",
    "BranchResolver",
    "DotfilesManager",
]
