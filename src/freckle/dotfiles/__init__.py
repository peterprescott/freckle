"""Dotfiles management package."""

from .branch import BranchResolver
from .manager import DotfilesManager
from .repo import BareGitRepo
from .types import (
    AddFilesResult,
    BranchInfo,
    CommitPushResult,
    SyncStatus,
)

__all__ = [
    "AddFilesResult",
    "BareGitRepo",
    "BranchInfo",
    "BranchResolver",
    "CommitPushResult",
    "DotfilesManager",
    "SyncStatus",
]
