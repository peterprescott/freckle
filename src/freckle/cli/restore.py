"""Restore command for freckle CLI."""

import difflib
import subprocess
from pathlib import Path
from typing import List, Optional

import typer

from freckle.backup import BackupManager
from freckle.dotfiles import GitHistoryService

from .helpers import (
    env,
    get_config,
    get_dotfiles_dir,
    normalize_to_home_relative,
)
from .history import resolve_to_repo_paths
from .output import (
    console,
    diff_add,
    diff_context,
    diff_remove,
    error,
    info,
    muted,
    plain,
    success,
    warning,
)


def get_history_service(dotfiles_dir: Path) -> GitHistoryService:
    """Create a GitHistoryService for the dotfiles repo."""
    return GitHistoryService(dotfiles_dir, env.home)


def get_tracked_files(dotfiles_dir: Path) -> List[str]:
    """Get list of tracked files in the dotfiles repo."""
    try:
        result = subprocess.run(
            [
                "git",
                "--git-dir",
                str(dotfiles_dir),
                "--work-tree",
                str(env.home),
                "ls-files",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(env.home),  # Must run from work-tree
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split("\n")
            return [f.strip() for f in lines if f.strip()]
    except Exception:
        pass
    return []


def is_file_or_tool(identifier: str, dotfiles_dir: Path, config) -> bool:
    """Check if identifier is a file path or tool name (not a commit hash)."""
    # Explicit path indicators
    if identifier.startswith(("/", "./", "../", "~")):
        return True
    if identifier.startswith(".") and "/" not in identifier:
        # Dotfile like .zshrc
        return True
    if "/" in identifier:
        return True

    # Check if it's a tracked file
    tracked = get_tracked_files(dotfiles_dir)
    normalized = normalize_to_home_relative(identifier, prefer_existing=True)
    if normalized in tracked or identifier in tracked:
        return True

    # Check if it's a tool name with config files
    if config and hasattr(config, "tools"):
        tool_def = config.tools.get(identifier)
        if tool_def and tool_def.get("config"):
            return True

    return False


def register(app: typer.Typer) -> None:
    """Register restore command with the app."""
    app.command()(restore)


def restore(
    identifier: Optional[str] = typer.Argument(
        None,
        help="Git commit hash or restore point (date/timestamp prefix)",
    ),
    tool_or_path: Optional[str] = typer.Argument(
        None,
        help="Tool name or file path to restore (for git commits)",
    ),
    files: Optional[List[str]] = typer.Option(
        None,
        "--file",
        "-f",
        help="Specific file(s) to restore (can be repeated)",
    ),
    list_points: bool = typer.Option(
        False,
        "--list",
        "-l",
        help="List available restore points",
    ),
    delete: Optional[str] = typer.Option(
        None,
        "--delete",
        help="Delete a restore point by identifier",
    ),
    all_files: bool = typer.Option(
        False,
        "--all",
        help="Restore all files changed in the commit",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show what would be restored without making changes",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-y",
        help="Skip confirmation prompts",
    ),
):
    """Restore files to last committed version, from a commit, or from backup.

    Supports three modes:

    1. File restore: Restore a file to its last committed (HEAD) version.
       Just specify the file path or tool name.

    2. Git commit restore: Restore dotfiles from a specific git commit.
       Use 'freckle history <tool>' to find commit hashes.

    3. Backup restore: Restore from automatic backup points created
       before sync or force-checkout operations.

    Examples:
        freckle restore .zshrc              # Restore file to HEAD
        freckle restore ~/.config/nvim/     # Restore directory to HEAD
        freckle restore nvim                # Restore tool's configs to HEAD

        freckle restore abc123f nvim        # Restore nvim from commit
        freckle restore abc123f --all       # All files in commit

        freckle restore --list              # List backup restore points
        freckle restore 2026-01-25          # Restore from backup date
    """
    manager = BackupManager()

    # Handle --list
    if list_points:
        points = manager.list_restore_points()

        if not points:
            plain("No restore points available.")
            muted(
                "\nRestore points are created automatically before "
                "sync or force-checkout."
            )
            return

        plain("Available restore points:\n")
        for point in points:
            file_count = len(point.files)
            plain(
                f"  {point.display_time} - {point.reason} ({file_count} files)"
            )

        muted(
            f"\nTo restore: freckle restore <date>  "
            f"(e.g. {points[0].timestamp[:10]})"
        )
        return

    # Handle --delete
    if delete:
        point = manager.get_restore_point(delete)
        if not point:
            error(f"Restore point not found: {delete}")
            raise typer.Exit(1)

        if manager.delete_restore_point(point):
            success(f"Deleted restore point from {point.display_time}")
        else:
            error("Failed to delete restore point")
            raise typer.Exit(1)
        return

    # Restore requires identifier
    if not identifier:
        error("Usage: freckle restore <file|commit|date>")
        plain("\nExamples:")
        muted("  freckle restore .zshrc         # Restore file to HEAD")
        muted("  freckle restore nvim           # Restore tool to HEAD")
        muted("  freckle restore abc123f nvim       # Restore from git commit")
        muted("  freckle restore 2026-01-25         # Restore from backup")
        muted("\nRun 'freckle restore --list' to see backup restore points.")
        muted("Run 'freckle history <tool>' to see git commit history.")
        raise typer.Exit(1)

    # Determine if identifier is a git commit or backup restore point
    config = get_config()
    dotfiles_dir = get_dotfiles_dir(config)

    # Priority: file/tool > commit hash > backup restore point
    if (
        dotfiles_dir.exists()
        and not tool_or_path  # No second argument means file restore mode
        and is_file_or_tool(identifier, dotfiles_dir, config)
    ):
        # NEW: Restore file/tool to HEAD
        restore_to_head(
            identifier,
            dry_run,
            force,
            config,
            dotfiles_dir,
            manager,
        )
    elif dotfiles_dir.exists() and is_git_commit(dotfiles_dir, identifier):
        # Git commit-based restore
        restore_from_commit(
            identifier,
            tool_or_path,
            all_files,
            dry_run,
            force,
            files,
            config,
            dotfiles_dir,
            manager,
        )
    else:
        # Backup-based restore (legacy mode)
        restore_from_backup(
            identifier,
            files,
            manager,
        )


def is_git_commit(dotfiles_dir: Path, identifier: str) -> bool:
    """Check if identifier is a valid git commit hash."""
    try:
        result = subprocess.run(
            [
                "git",
                "--git-dir",
                str(dotfiles_dir),
                "rev-parse",
                "--verify",
                f"{identifier}^{{commit}}",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


def get_commit_files(dotfiles_dir: Path, commit_hash: str) -> List[str]:
    """Get list of files changed in a commit."""
    try:
        result = subprocess.run(
            [
                "git",
                "--git-dir",
                str(dotfiles_dir),
                "diff-tree",
                "--no-commit-id",
                "--name-only",
                "-r",
                commit_hash,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return []
        return [
            f.strip() for f in result.stdout.strip().split("\n") if f.strip()
        ]
    except Exception:
        return []


def get_file_at_commit(
    dotfiles_dir: Path,
    commit_hash: str,
    file_path: str,
) -> Optional[str]:
    """Get file contents from a specific commit."""
    try:
        result = subprocess.run(
            [
                "git",
                "--git-dir",
                str(dotfiles_dir),
                "show",
                f"{commit_hash}:{file_path}",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return None
        return result.stdout
    except Exception:
        return None


def show_diff(current_content: str, new_content: str, file_path: str) -> None:
    """Display a colorized diff between current and new content."""
    current_lines = current_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)

    diff = difflib.unified_diff(
        current_lines,
        new_lines,
        fromfile=f"current: {file_path}",
        tofile=f"from commit: {file_path}",
    )

    for line in diff:
        if line.startswith("+") and not line.startswith("+++"):
            diff_add(line.rstrip())
        elif line.startswith("-") and not line.startswith("---"):
            diff_remove(line.rstrip())
        elif line.startswith("@@"):
            info(line.rstrip())
        else:
            diff_context(line.rstrip())


def restore_to_head(
    identifier: str,
    dry_run: bool,
    force: bool,
    config,
    dotfiles_dir: Path,
    manager: BackupManager,
) -> None:
    """Restore file(s) to their HEAD (last committed) version."""
    tracked = get_tracked_files(dotfiles_dir)

    # Resolve identifier to list of files
    files_to_restore: List[str] = []

    # Check if it's a tool name with config files
    if config and hasattr(config, "tools"):
        tool_def = config.tools.get(identifier)
        if tool_def and tool_def.get("config"):
            tool_configs = tool_def.get("config", [])
            for cfg in tool_configs:
                if cfg in tracked:
                    files_to_restore.append(cfg)
            if files_to_restore:
                plain(f"Restoring {identifier} config files to HEAD:\n")

    # If not a tool, treat as file path
    if not files_to_restore:
        normalized = normalize_to_home_relative(
            identifier, prefer_existing=True
        )
        if normalized and normalized in tracked:
            files_to_restore = [normalized]
        elif identifier in tracked:
            files_to_restore = [identifier]
        else:
            # Check if it's a directory prefix
            prefix = normalized or identifier
            if not prefix.endswith("/"):
                prefix += "/"
            matching = [f for f in tracked if f.startswith(prefix)]
            if matching:
                files_to_restore = matching
                plain(f"Restoring {len(matching)} files under {identifier}:\n")

    if not files_to_restore:
        error(f"'{identifier}' is not tracked by freckle")
        muted("\nTracked files can be listed with: freckle files list")
        raise typer.Exit(1)

    # Get HEAD content for each file and check for changes
    restore_items: List[tuple] = []  # (path, head_content, has_changes)

    for file_path in files_to_restore:
        head_content = get_file_at_commit(dotfiles_dir, "HEAD", file_path)
        if head_content is None:
            warning(f"  {file_path} - not in HEAD (skipping)")
            continue

        target_path = env.home / file_path
        has_changes = False
        current_content = ""

        if target_path.exists():
            try:
                current_content = target_path.read_text()
                has_changes = current_content != head_content
            except Exception:
                has_changes = True
        else:
            has_changes = True  # File doesn't exist locally

        item = (file_path, head_content, has_changes, current_content)
        restore_items.append(item)

    # Filter to only files with changes
    changed_items = [(p, h, c) for p, h, ch, c in restore_items if ch]

    if not changed_items:
        success("All files already match HEAD (no changes needed)")
        return

    # Show what will be restored
    plain(f"Files to restore ({len(changed_items)}):\n")
    for file_path, head_content, current_content in changed_items:
        console.print(f"  [bold]{file_path}[/bold]")
        target_path = env.home / file_path
        if target_path.exists():
            current_lines = len(current_content.splitlines())
            head_lines = len(head_content.splitlines())
            muted(f"    {current_lines} lines → {head_lines} lines")
        else:
            muted("    (will be created)")

    plain("")

    if dry_run:
        plain("[Dry run - no changes made]")
        return

    # Confirm unless --force
    if not force:
        if not typer.confirm("Restore these files to HEAD?"):
            plain("Cancelled.")
            raise typer.Exit(0)

    # Create backup before restoring
    files_for_backup = [
        p for p, _, _ in changed_items if (env.home / p).exists()
    ]
    if files_for_backup:
        backup_point = manager.create_restore_point(
            files_for_backup,
            "pre-restore to HEAD",
            env.home,
        )
        if backup_point:
            muted(f"Backed up to: {backup_point.path}")

    # Perform the restore
    restored_count = 0
    for file_path, head_content, _ in changed_items:
        target_path = env.home / file_path
        target_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            target_path.write_text(head_content)
            restored_count += 1
            success(f"Restored {file_path}")
        except Exception as e:
            error(f"Failed to restore {file_path}: {e}")

    if restored_count > 0:
        success(f"\nRestored {restored_count} file(s) to HEAD")


def restore_from_commit(
    commit_hash: str,
    tool_or_path: Optional[str],
    all_files: bool,
    dry_run: bool,
    force: bool,
    explicit_files: Optional[List[str]],
    config,
    dotfiles_dir: Path,
    manager: BackupManager,
) -> None:
    """Restore files from a git commit."""
    # Use the history service for git operations
    history_svc = get_history_service(dotfiles_dir)

    # Determine which files to restore
    if all_files:
        # Restore all files changed in the commit
        files_to_restore = history_svc.get_commit_files(commit_hash)
        if not files_to_restore:
            error(f"No files found in commit {commit_hash}")
            raise typer.Exit(1)
    elif explicit_files:
        # Use explicitly specified files
        files_to_restore = []
        for f in explicit_files:
            relative = normalize_to_home_relative(f, prefer_existing=True)
            files_to_restore.append(relative if relative else f)
    elif tool_or_path:
        # Resolve tool name or path to repo-relative paths
        files_to_restore = resolve_to_repo_paths(
            tool_or_path, config, dotfiles_dir
        )
    else:
        # Interactive mode: restore all files from commit (typically just one)
        files_to_restore = history_svc.get_commit_files(commit_hash)
        if not files_to_restore:
            error(f"No files found in commit {commit_hash}")
            raise typer.Exit(1)

    # Get commit info
    commit_info = history_svc.get_commit_subject(commit_hash)

    plain(f"Restoring from commit {commit_hash}")
    if commit_info:
        muted(f"  {commit_info}")
    plain("")

    # Validate files exist in commit
    valid_files = []
    for f in files_to_restore:
        content = history_svc.get_file_at_commit(commit_hash, f)
        if content is not None:
            valid_files.append((f, content))
        else:
            warning(f"{f} - not found in commit", prefix="  ⚠")

    if not valid_files:
        error("No valid files to restore from this commit.")
        raise typer.Exit(1)

    plain(f"Files to restore ({len(valid_files)}):\n")

    # Show each file and its diff
    for file_path, new_content in valid_files:
        target_path = env.home / file_path

        console.print(f"  [bold]{file_path}[/bold]")

        if target_path.exists():
            try:
                current_content = target_path.read_text()
                if current_content == new_content:
                    muted("    (no changes needed)")
                else:
                    plain("    Changes:")
                    # Show condensed diff info
                    current_lines = len(current_content.splitlines())
                    new_lines = len(new_content.splitlines())
                    muted(f"      {current_lines} lines → {new_lines} lines")
            except Exception:
                muted("    (could not read current file)")
        else:
            muted("    (file does not exist, will be created)")

    plain("")

    if dry_run:
        plain("[Dry run - no changes made]")
        muted("\nTo apply these changes, run without --dry-run")
        return

    # Confirm unless --force
    if not force:
        if not typer.confirm("Restore these files?"):
            plain("Cancelled.")
            raise typer.Exit(0)

    # Create backup before restoring
    files_for_backup = [f for f, _ in valid_files if (env.home / f).exists()]
    if files_for_backup:
        backup_point = manager.create_restore_point(
            files_for_backup,
            f"pre-restore from {commit_hash[:7]}",
            env.home,
        )
        if backup_point:
            success("Backed up current files to:")
            muted(f"    {backup_point.path}")

    # Perform the restore
    restored_count = 0
    for file_path, new_content in valid_files:
        target_path = env.home / file_path

        # Check if content is the same
        if target_path.exists():
            try:
                if target_path.read_text() == new_content:
                    continue  # Skip unchanged files
            except Exception:
                pass

        # Ensure parent directory exists
        target_path.parent.mkdir(parents=True, exist_ok=True)

        # Write the file
        try:
            target_path.write_text(new_content)
            restored_count += 1
            success(f"Restored {file_path}")
        except Exception as e:
            error(f"Failed to restore {file_path}: {e}")

    if restored_count > 0:
        success(f"Restored {restored_count} file(s) from {commit_hash[:7]}")
    else:
        muted("\nNo files needed restoration (all up to date).")


def get_commit_info(dotfiles_dir: Path, commit_hash: str) -> Optional[str]:
    """Get commit subject line."""
    try:
        result = subprocess.run(
            [
                "git",
                "--git-dir",
                str(dotfiles_dir),
                "log",
                "-1",
                "--format=%s",
                commit_hash,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def restore_from_backup(
    identifier: str,
    files: Optional[List[str]],
    manager: BackupManager,
) -> None:
    """Restore files from a backup restore point (legacy mode)."""
    point = manager.get_restore_point(identifier)
    if not point:
        error(f"Restore point not found: {identifier}")
        muted("\nRun 'freckle restore --list' to see available points.")
        muted("If this is a git commit, ensure your dotfiles repo exists.")
        raise typer.Exit(1)

    # Show what we're about to restore
    files_to_restore = files if files else point.files

    plain(f"Restoring from {point.display_time} ({point.reason}):\n")

    # Validate requested files exist in restore point
    if files:
        missing = [f for f in files if f not in point.files]
        if missing:
            warning("These files are not in the restore point:")
            for f in missing:
                muted(f"  - {f}")
            plain("")

        files_to_restore = [f for f in files if f in point.files]
        if not files_to_restore:
            error("No matching files to restore.")
            raise typer.Exit(1)

    for f in files_to_restore:
        plain(f"  {f}")

    plain("")

    # Confirm
    if not typer.confirm("Restore these files?"):
        plain("Cancelled.")
        raise typer.Exit(0)

    # Do the restore
    restored = manager.restore(point, env.home, files_to_restore)

    if restored:
        success(f"Restored {len(restored)} file(s):")
        for f in restored:
            muted(f"    {f}")
    else:
        error("No files were restored.")
        raise typer.Exit(1)
