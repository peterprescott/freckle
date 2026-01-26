"""Type definitions for dotfiles module."""

from typing import List, Optional

from typing_extensions import NotRequired, TypedDict


class BranchInfo(TypedDict):
    """Information about branch resolution."""

    configured: str
    effective: str
    reason: str
    message: NotRequired[str]


class SyncStatus(TypedDict):
    """Detailed sync status of the dotfiles repository."""

    initialized: bool
    branch: NotRequired[str]
    branch_info: NotRequired[BranchInfo]
    has_local_changes: NotRequired[bool]
    changed_files: NotRequired[List[str]]
    is_ahead: NotRequired[bool]
    is_behind: NotRequired[bool]
    ahead_count: NotRequired[int]
    behind_count: NotRequired[int]
    local_commit: NotRequired[Optional[str]]
    remote_commit: NotRequired[Optional[str]]
    fetch_failed: NotRequired[bool]
    remote_branch_missing: NotRequired[bool]


class AddFilesResult(TypedDict):
    """Result of adding files to the repository."""

    success: bool
    added: NotRequired[List[str]]
    skipped: NotRequired[List[str]]
    error: NotRequired[str]


class CommitPushResult(TypedDict):
    """Result of commit and push operation."""

    success: bool
    committed: NotRequired[bool]
    pushed: NotRequired[bool]
    error: NotRequired[str]
