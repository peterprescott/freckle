"""Restore command for freckle CLI."""

import difflib
import subprocess
from pathlib import Path
from typing import List, Optional

import typer

from freckle.backup import BackupManager
from freckle.dotfiles import GitHistoryService

from .helpers import env, get_config, get_dotfiles_dir
from .history import resolve_to_repo_paths


def get_history_service(dotfiles_dir: Path) -> GitHistoryService:
    """Create a GitHistoryService for the dotfiles repo."""
    return GitHistoryService(dotfiles_dir, env.home)


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
    """Restore files from a git commit or backup restore point.

    Supports two modes:

    1. Git commit restore: Restore dotfiles from a specific git commit.
       Use 'freckle history <tool>' to find commit hashes.

    2. Backup restore: Restore from automatic backup points created
       before sync or force-checkout operations.

    Examples:
        freckle restore abc123f nvim        # Restore nvim from commit
        freckle restore abc123f ~/.zshrc    # Restore file from commit
        freckle restore abc123f --all       # All files in commit
        freckle restore abc123f --dry-run   # Preview changes

        freckle restore --list              # List backup restore points
        freckle restore 2026-01-25          # Restore from backup date
        freckle restore 2026-01-25 -f .zshrc  # Specific file from backup
    """
    manager = BackupManager()

    # Handle --list
    if list_points:
        points = manager.list_restore_points()

        if not points:
            typer.echo("No restore points available.")
            typer.echo(
                "\nRestore points are created automatically before "
                "sync or force-checkout."
            )
            return

        typer.echo("Available restore points:\n")
        for point in points:
            file_count = len(point.files)
            typer.echo(
                f"  {point.display_time} - {point.reason} ({file_count} files)"
            )

        typer.echo(
            f"\nTo restore: freckle restore <date>  (e.g. {points[0].timestamp[:10]})"  # noqa: E501
        )
        return

    # Handle --delete
    if delete:
        point = manager.get_restore_point(delete)
        if not point:
            typer.echo(f"Restore point not found: {delete}", err=True)
            raise typer.Exit(1)

        if manager.delete_restore_point(point):
            typer.echo(f"✓ Deleted restore point from {point.display_time}")
        else:
            typer.echo("Failed to delete restore point", err=True)
            raise typer.Exit(1)
        return

    # Restore requires identifier
    if not identifier:
        typer.echo(
            "Usage: freckle restore <identifier> [tool_or_path]", err=True
        )
        typer.echo("\nExamples:")
        typer.echo(
            "  freckle restore abc123f nvim       # Restore from git commit"
        )
        typer.echo(
            "  freckle restore 2026-01-25         # Restore from backup"
        )
        typer.echo(
            "\nRun 'freckle restore --list' to see backup restore points."
        )
        typer.echo("Run 'freckle history <tool>' to see git commit history.")
        raise typer.Exit(1)

    # Determine if identifier is a git commit or backup restore point
    config = get_config()
    dotfiles_dir = get_dotfiles_dir(config)

    if dotfiles_dir.exists() and is_git_commit(dotfiles_dir, identifier):
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
            typer.echo(typer.style(line.rstrip(), fg=typer.colors.GREEN))
        elif line.startswith("-") and not line.startswith("---"):
            typer.echo(typer.style(line.rstrip(), fg=typer.colors.RED))
        elif line.startswith("@@"):
            typer.echo(typer.style(line.rstrip(), fg=typer.colors.CYAN))
        else:
            typer.echo(line.rstrip())


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
            typer.echo(f"No files found in commit {commit_hash}", err=True)
            raise typer.Exit(1)
    elif explicit_files:
        # Use explicitly specified files
        files_to_restore = []
        for f in explicit_files:
            expanded = Path(f).expanduser()
            try:
                relative = expanded.relative_to(env.home)
                files_to_restore.append(str(relative))
            except ValueError:
                files_to_restore.append(f)
    elif tool_or_path:
        # Resolve tool name or path to repo-relative paths
        files_to_restore = resolve_to_repo_paths(
            tool_or_path, config, dotfiles_dir
        )
    else:
        typer.echo("Error: Must specify a tool/path or use --all", err=True)
        typer.echo("\nExamples:")
        typer.echo(f"  freckle restore {commit_hash} nvim")
        typer.echo(f"  freckle restore {commit_hash} --all")
        raise typer.Exit(1)

    # Get commit info
    commit_info = history_svc.get_commit_subject(commit_hash)

    typer.echo(f"Restoring from commit {commit_hash}")
    if commit_info:
        typer.echo(f"  {commit_info}")
    typer.echo("")

    # Validate files exist in commit
    valid_files = []
    for f in files_to_restore:
        content = history_svc.get_file_at_commit(commit_hash, f)
        if content is not None:
            valid_files.append((f, content))
        else:
            typer.echo(
                typer.style(
                    f"  ⚠ {f} - not found in commit", fg=typer.colors.YELLOW
                )
            )

    if not valid_files:
        typer.echo("\nNo valid files to restore from this commit.", err=True)
        raise typer.Exit(1)

    typer.echo(f"Files to restore ({len(valid_files)}):\n")

    # Show each file and its diff
    for file_path, new_content in valid_files:
        target_path = env.home / file_path

        typer.echo(typer.style(f"  {file_path}", bold=True))

        if target_path.exists():
            try:
                current_content = target_path.read_text()
                if current_content == new_content:
                    typer.echo(
                        typer.style("    (no changes needed)", dim=True)
                    )
                else:
                    typer.echo("    Changes:")
                    # Show condensed diff info
                    current_lines = len(current_content.splitlines())
                    new_lines = len(new_content.splitlines())
                    typer.echo(
                        typer.style(
                            f"      {current_lines} lines → {new_lines} lines",
                            dim=True,
                        )
                    )
            except Exception:
                typer.echo("    (could not read current file)")
        else:
            typer.echo(
                typer.style(
                    "    (file does not exist, will be created)", dim=True
                )
            )

    typer.echo("")

    if dry_run:
        typer.echo("[Dry run - no changes made]")
        typer.echo("\nTo apply these changes, run without --dry-run")
        return

    # Confirm unless --force
    if not force:
        if not typer.confirm("Restore these files?"):
            typer.echo("Cancelled.")
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
            typer.echo("\n✓ Backed up current files to:")
            typer.echo(f"    {backup_point.path}")

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
            typer.echo(f"✓ Restored {file_path}")
        except Exception as e:
            typer.echo(f"✗ Failed to restore {file_path}: {e}", err=True)

    if restored_count > 0:
        typer.echo(
            f"\n✓ Restored {restored_count} file(s) from {commit_hash[:7]}"
        )
    else:
        typer.echo("\nNo files needed restoration (all up to date).")


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
        typer.echo(f"Restore point not found: {identifier}", err=True)
        typer.echo(
            "\nRun 'freckle restore --list' to see available restore points."
        )
        typer.echo(
            "If this is a git commit, ensure your dotfiles repo exists."
        )
        raise typer.Exit(1)

    # Show what we're about to restore
    files_to_restore = files if files else point.files

    typer.echo(f"Restoring from {point.display_time} ({point.reason}):\n")

    # Validate requested files exist in restore point
    if files:
        missing = [f for f in files if f not in point.files]
        if missing:
            typer.echo("Warning: These files are not in the restore point:")
            for f in missing:
                typer.echo(f"  - {f}")
            typer.echo("")

        files_to_restore = [f for f in files if f in point.files]
        if not files_to_restore:
            typer.echo("No matching files to restore.", err=True)
            raise typer.Exit(1)

    for f in files_to_restore:
        typer.echo(f"  {f}")

    typer.echo("")

    # Confirm
    if not typer.confirm("Restore these files?"):
        typer.echo("Cancelled.")
        raise typer.Exit(0)

    # Do the restore
    restored = manager.restore(point, env.home, files_to_restore)

    if restored:
        typer.echo(f"\n✓ Restored {len(restored)} file(s):")
        for f in restored:
            typer.echo(f"    {f}")
    else:
        typer.echo("No files were restored.", err=True)
        raise typer.Exit(1)
