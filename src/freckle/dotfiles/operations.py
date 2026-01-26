"""File and commit operations for dotfiles repositories."""

import logging
from pathlib import Path
from typing import Callable, List, Optional

from .repo import BareGitRepo
from .types import AddFilesResult, CommitPushResult

logger = logging.getLogger(__name__)


def add_files(
    git: BareGitRepo,
    work_tree: Path,
    files: List[str],
) -> AddFilesResult:
    """Add files to be tracked in the dotfiles repository.

    Args:
        git: The bare git repo wrapper
        work_tree: Path to the work tree
        files: List of file paths relative to work tree

    Returns:
        Dictionary with result info:
        - success: Whether the operation completed
        - added: List of files successfully added
        - skipped: List of files that don't exist
        - error: Error message if operation failed
    """
    added: List[str] = []
    skipped: List[str] = []
    error: Optional[str] = None

    if not git.git_dir.exists():
        return AddFilesResult(
            success=False,
            added=[],
            skipped=[],
            error="Dotfiles repository not initialized",
        )

    for f in files:
        file_path = work_tree / f
        if not file_path.exists():
            skipped.append(f)
            continue

        try:
            add_result = git.run("add", f, check=False)
            if add_result.returncode != 0:
                logger.warning(f"Failed to add {f}: {add_result.stderr}")
                skipped.append(f)
            else:
                added.append(f)
        except Exception as e:
            logger.warning(f"Error adding {f}: {e}")
            skipped.append(f)

    success = len(added) > 0 or len(skipped) == len(files)
    result: AddFilesResult = {
        "success": success,
        "added": added,
        "skipped": skipped,
    }
    if error is not None:
        result["error"] = error
    return result


def commit_and_push(
    git: BareGitRepo,
    branch: str,
    message: str,
    get_changed_files: Callable[[], List[str]],
) -> CommitPushResult:
    """Commit local changes to tracked files and push to remote.

    Args:
        git: The bare git repo wrapper
        branch: The branch name to commit/push to
        message: Commit message
        get_changed_files: Callable that returns list of changed files

    Returns:
        Dictionary with result info:
        - success: Whether the operation completed successfully
        - committed: Whether a commit was made
        - pushed: Whether the push succeeded
        - error: Error message if any step failed
    """
    changed = get_changed_files()
    if not changed:
        return CommitPushResult(
            success=True,
            committed=False,
            pushed=False,
            error="No changes to commit",
        )

    try:
        add_result = git.run("add", "-u", check=False)
        if add_result.returncode != 0:
            return CommitPushResult(
                success=False,
                committed=False,
                pushed=False,
                error=f"git add failed: {add_result.stderr.strip()}",
            )

        commit_result = git.run("commit", "-m", message, check=False)
        if commit_result.returncode != 0:
            if (
                "nothing to commit" in commit_result.stdout
                or "nothing to commit" in commit_result.stderr
            ):
                return CommitPushResult(
                    success=True,
                    committed=False,
                    pushed=False,
                    error="No changes to commit",
                )
            return CommitPushResult(
                success=False,
                committed=False,
                pushed=False,
                error=f"git commit failed: {commit_result.stderr.strip()}",
            )

        logger.info(f"Created commit on {branch}")

    except Exception as e:
        return CommitPushResult(
            success=False,
            committed=False,
            pushed=False,
            error=f"Commit failed: {e}",
        )

    # Push
    try:
        push_result = git.run_bare(
            "push", "origin", branch, check=False, timeout=60
        )
        if push_result.returncode == 0:
            logger.info(f"Pushed to origin/{branch}")
            return CommitPushResult(
                success=True,
                committed=True,
                pushed=True,
            )
        else:
            error = f"Push failed: {push_result.stderr.strip()}"
            logger.error(error)
            return CommitPushResult(
                success=False,
                committed=True,
                pushed=False,
                error=error,
            )
    except Exception as e:
        error = f"Push failed: {e}"
        logger.error(error)
        return CommitPushResult(
            success=False,
            committed=True,
            pushed=False,
            error=error,
        )


def push(git: BareGitRepo, branch: str) -> CommitPushResult:
    """Push local commits to remote.

    Args:
        git: The bare git repo wrapper
        branch: The branch name to push

    Returns:
        Dictionary with result info:
        - success: Whether push succeeded
        - error: Error message if failed
    """
    try:
        push_result = git.run_bare(
            "push", "-u", "origin", branch, check=False, timeout=60
        )
        if push_result.returncode == 0:
            logger.info(f"Pushed to origin/{branch}")
            return CommitPushResult(success=True)
        else:
            error = push_result.stderr.strip()
            logger.error(f"Push failed: {error}")
            return CommitPushResult(success=False, error=error)
    except Exception as e:
        error = str(e)
        logger.error(f"Push failed: {e}")
        return CommitPushResult(success=False, error=error)


def force_checkout(git: BareGitRepo, branch: str):
    """Discard local changes and update to match remote.

    Args:
        git: The bare git repo wrapper
        branch: The branch to reset to
    """
    logger.info("Fetching latest from remote...")
    git.fetch()

    try:
        git.run("reset", "--hard", f"origin/{branch}")
        logger.info(f"Reset to origin/{branch}")
    except Exception as e:
        raise RuntimeError(f"Reset failed: {e}")
