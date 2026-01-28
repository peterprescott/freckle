"""Track, untrack, and propagate file commands for freckle CLI."""

import subprocess
from typing import List, Optional

import typer

from .helpers import (
    env,
    get_config,
    get_secret_scanner,
    normalize_to_home_relative,
    require_dotfiles_ready,
)
from .output import console, error, muted, plain, plain_err, success, warning


def register(app: typer.Typer) -> None:
    """Register file commands with the app."""
    app.command()(track)
    app.command()(untrack)
    app.command()(propagate)


def _auto_save(dotfiles, files: List[str], action: str) -> bool:
    """Auto-commit and push after track/untrack. Returns True if pushed."""
    # Build commit message
    if len(files) == 1:
        msg = f"{action} {files[0]}"
    else:
        msg = f"{action} {len(files)} file(s)"

    # Commit
    try:
        dotfiles._git.run("commit", "-m", msg)
    except subprocess.CalledProcessError:
        return False  # Nothing to commit

    # Try to push (don't fail if offline)
    try:
        result = dotfiles.push()
        return result.get("success", False)
    except Exception:
        return False


def track(
    files: List[str] = typer.Argument(
        ..., help="Files to start tracking"
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Track files even if they appear to contain secrets",
    ),
):
    """Start tracking files in your dotfiles.

    Adds files to your dotfiles repository and saves them to the cloud.

    Examples:
        freckle track .zshrc
        freckle track .vimrc .bashrc
        freckle track .config/starship.toml
        freckle track ~/.config/nvim/init.lua
    """

    if not files:
        plain("Usage: freckle track <file> [file2] [file3] ...")
        raise typer.Exit(1)

    config = get_config()
    dotfiles, _ = require_dotfiles_ready(config)

    # Convert user-provided paths to paths relative to home directory
    home_relative_files = []
    for f in files:
        relative = normalize_to_home_relative(f, prefer_existing=False)
        if relative is None:
            error(f"File must be under home directory: {f}")
            continue
        home_relative_files.append(relative)

    if not home_relative_files:
        raise typer.Exit(1)

    # Check for secrets unless --force is used
    if not force:
        scanner = get_secret_scanner(config)
        secrets_found = scanner.scan_files(home_relative_files, env.home)

        if secrets_found:
            error(
                f"Blocked: {len(secrets_found)} file(s) appear to "
                "contain secrets:"
            )
            plain_err("")
            for match in secrets_found:
                plain_err(f"  {match.file}")
                plain_err(f"    └─ {match.reason}")
                if match.line:
                    plain_err(f"       (line {match.line})")

            plain_err("\nSecrets should not be tracked in dotfiles.")
            plain_err("To override: freckle track --force <files>")
            raise typer.Exit(1)

    result = dotfiles.add_files(home_relative_files)

    if result["added"]:
        success(f"Now tracking {len(result['added'])} file(s):")
        for f in result["added"]:
            console.print(f"    [green]+[/green] {f}")

        # Auto-save
        pushed = _auto_save(dotfiles, result["added"], "Track")
        if pushed:
            success("Synced to cloud")
        else:
            success("Saved locally")
            muted("  (Run 'freckle save' to sync when online)")

    if result["skipped"]:
        warning(f"Skipped {len(result['skipped'])} file(s):")
        for f in result["skipped"]:
            file_path = env.home / f
            if not file_path.exists():
                muted(f"    - {f} (file not found)")
            else:
                muted(f"    - {f} (failed to add)")

    if not result["added"]:
        raise typer.Exit(1)


def untrack(
    files: List[str] = typer.Argument(..., help="Files to stop tracking"),
    delete: bool = typer.Option(
        False, "--delete", help="Also delete the file from home directory"
    ),
):
    """Stop tracking files in your dotfiles.

    By default, the file is kept in your home directory but removed from
    tracking. Use --delete to also remove the file.

    Examples:
        freckle untrack .bashrc              # Stop tracking, keep file
        freckle untrack .old-config --delete # Stop tracking and delete
    """

    if not files:
        plain("Usage: freckle untrack <file> [file2] ...")
        raise typer.Exit(1)

    config = get_config()
    dotfiles, _ = require_dotfiles_ready(config)

    # Convert user-provided paths to paths relative to home directory
    home_relative_files = []
    for f in files:
        relative = normalize_to_home_relative(f, prefer_existing=True)
        if relative is None:
            error(f"File must be under home directory: {f}")
            continue
        home_relative_files.append(relative)

    if not home_relative_files:
        raise typer.Exit(1)

    removed = []
    skipped = []

    for f in home_relative_files:
        try:
            if delete:
                # Remove from git and delete file
                dotfiles._git.run("rm", f)
            else:
                # Remove from git but keep file
                dotfiles._git.run("rm", "--cached", f)
            removed.append(f)
        except subprocess.CalledProcessError as e:
            skipped.append((f, str(e)))

    if removed:
        if delete:
            success(f"Stopped tracking and deleted {len(removed)} file(s):")
        else:
            success(f"Stopped tracking {len(removed)} file(s):")
        for f in removed:
            if delete:
                console.print(f"    [red]-[/red] {f} (deleted)")
            else:
                console.print(f"    [dim]-[/dim] {f} (kept in ~/)")

        # Auto-save
        pushed = _auto_save(dotfiles, removed, "Untrack")
        if pushed:
            success("Synced to cloud")
        else:
            success("Saved locally")
            muted("  (Run 'freckle save' to sync when online)")

    if skipped:
        warning(f"Failed to untrack {len(skipped)} file(s):")
        for f, err in skipped:
            muted(f"    - {f}: {err}")

    if not removed:
        raise typer.Exit(1)


def propagate(
    file: str = typer.Argument(
        ..., help="File to propagate to other branches"
    ),
    to: Optional[List[str]] = typer.Option(
        None, "--to", "-t",
        help="Target branch(es). Defaults to all profile branches."
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Skip confirmation"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", "-n", help="Show what would happen"
    ),
    push: bool = typer.Option(
        False, "--push", "-p", help="Push changes after propagating"
    ),
):
    """Propagate a file to other profile branches.

    Copies a file from the current branch to other profile branches,
    creating a commit on each.

    Examples:
        freckle propagate .config/nvim/init.lua
        freckle propagate .zshrc --to linux --to main
        freckle propagate .config/starship.toml --push
    """
    config = get_config()
    profiles = config.get_profiles()

    if not profiles:
        plain("No profiles configured.")
        return

    dotfiles, _ = require_dotfiles_ready(config)

    # Normalize file path to be relative to home
    relative_path = normalize_to_home_relative(file, prefer_existing=True)
    if relative_path is None:
        error(f"File must be under home directory: {file}")
        raise typer.Exit(1)

    # Get current branch
    try:
        result = dotfiles._git.run("rev-parse", "--abbrev-ref", "HEAD")
        current_branch = result.stdout.strip()
    except subprocess.CalledProcessError:
        error("Failed to get current branch.")
        raise typer.Exit(1)

    # Get file content from current branch
    try:
        git_path = f"{current_branch}:{relative_path}"
        result = dotfiles._git.run("show", git_path)
        file_content = result.stdout
    except subprocess.CalledProcessError:
        error(f"File not found in current branch: {relative_path}")
        raise typer.Exit(1)

    # Determine target branches
    if to:
        # Validate specified branches exist as profiles
        branches_to_update = []
        for branch in to:
            if branch not in profiles:
                warning(f"'{branch}' is not a profile branch")
            if branch != current_branch:
                branches_to_update.append(branch)
    else:
        # All profile branches except current
        branches_to_update = [
            name for name in profiles if name != current_branch
        ]

    if not branches_to_update:
        plain("No other branches to update.")
        return

    n = len(branches_to_update)
    plain(
        f"Propagating {relative_path} from '{current_branch}' "
        f"to {n} branch(es):"
    )
    for branch in branches_to_update:
        muted(f"  - {branch}")

    if dry_run:
        plain("\n--- Dry run, no changes made ---")
        return

    if not force:
        if not typer.confirm("\nProceed?"):
            plain("Cancelled.")
            return

    plain("")

    # Check for uncommitted changes
    try:
        result = dotfiles._git.run("status", "--porcelain")
        output = result.stdout.strip()
        if output:
            tracked_changes = [
                line for line in output.split("\n")
                if line and not line.startswith("??")
            ]
            has_changes = bool(tracked_changes)
        else:
            has_changes = False
    except subprocess.CalledProcessError:
        has_changes = False

    stashed = False
    if has_changes:
        plain("Stashing local changes...")
        try:
            dotfiles._git.run("stash", "push", "-m", "freckle propagate")
            stashed = True
        except subprocess.CalledProcessError:
            error("Failed to stash changes.")
            raise typer.Exit(1)

    updated = []
    failed = []

    try:
        for branch in branches_to_update:
            try:
                # Checkout branch
                dotfiles._git.run("checkout", branch)

                # Write file
                target_file = dotfiles.work_tree / relative_path
                target_file.parent.mkdir(parents=True, exist_ok=True)
                target_file.write_text(file_content)

                # Stage and commit
                dotfiles._git.run("add", relative_path)
                dotfiles._git.run(
                    "commit", "-m",
                    f"Propagate {relative_path} from {current_branch}"
                )

                updated.append(branch)
                success(branch, prefix="  ✓")

            except subprocess.CalledProcessError:
                failed.append(branch)
                error(f"{branch} - failed", prefix="  ✗")

    finally:
        # Return to original branch
        try:
            dotfiles._git.run("checkout", current_branch)
        except subprocess.CalledProcessError:
            warning(f"Failed to return to {current_branch}")

        # Restore stashed changes
        if stashed:
            try:
                dotfiles._git.run("stash", "pop")
            except subprocess.CalledProcessError:
                warning("Failed to restore stashed changes")

    plain("")

    if updated:
        success(f"Updated {len(updated)} branch(es).")

        if push:
            plain("\nPushing changes...")
            for branch in updated:
                try:
                    dotfiles._git.run("push", "origin", branch)
                    success(f"Pushed {branch}", prefix="  ✓")
                except subprocess.CalledProcessError:
                    error(f"Failed to push {branch}", prefix="  ✗")
        else:
            muted("\nTo sync changes, run: freckle save")

    if failed:
        error(f"Failed to update {len(failed)} branch(es).")
        raise typer.Exit(1)
