"""Dotfiles management package."""

from .branch import BranchResolver
from .manager import DotfilesManager
from .repo import BareGitRepo

__all__ = [
    "BareGitRepo",
    "BranchResolver",
    "DotfilesManager",
]
