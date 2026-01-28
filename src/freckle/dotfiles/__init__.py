"""Dotfiles management package."""

from .branch import BranchResolver
from .history import CommitInfo, GitHistoryService
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
    "CommitInfo",
    "CommitPushResult",
    "DotfilesManager",
    "GitHistoryService",
    "SyncStatus",
]
