"""Save command for committing and pushing dotfiles changes."""

import subprocess
from typing import List, Optional

import typer

from .helpers import (
    CONFIG_FILENAME,
    env,
    get_config,
    get_dotfiles_dir,
    get_dotfiles_manager,
    get_secret_scanner,
)
from .output import (
    error,
    muted,
    plain,
    plain_err,
    success,
)


def register(app: typer.Typer) -> None:
    """Register save command with the app."""
    app.command()(save)


def _get_local_branches(dotfiles) -> List[str]:
    """Get all local branches in the dotfiles repo."""
    try:
        result = dotfiles._git.run("branch", "--list")
        branches = [
            b.strip().lstrip("* ")
            for b in result.stdout.split("\n")
            if b.strip()
        ]
        return branches
    except subprocess.CalledProcessError:
        return []


def _sync_config_to_all_branches(dotfiles, quiet: bool):
    """Sync config to ALL local branches (not just profiles in config).

    This ensures .freckle.yaml is identical across all local branches,
    making branches authoritative for profile existence.
    """
    # Get current branch
    try:
        result = dotfiles._git.run("rev-parse", "--abbrev-ref", "HEAD")
        current_branch = result.stdout.strip()
    except subprocess.CalledProcessError:
        return

    # Get current config content
    config_path = dotfiles.work_tree / CONFIG_FILENAME
    if not config_path.exists():
        return
    current_content = config_path.read_text()

    # Get ALL local branches (authoritative)
    all_branches = _get_local_branches(dotfiles)
    branches_to_update = [b for b in all_branches if b != current_branch]

    if not branches_to_update:
        return

    if not quiet:
        plain(f"\nSyncing {CONFIG_FILENAME} to {len(branches_to_update)} "
              "branch(es)...")

    synced = []
    for branch in branches_to_update:
        try:
            # Checkout branch
            dotfiles._git.run("checkout", branch)

            # Write config
            config_path.write_text(current_content)

            # Stage and commit
            dotfiles._git.run("add", CONFIG_FILENAME)
            try:
                dotfiles._git.run(
                    "commit", "-m",
                    f"Sync {CONFIG_FILENAME} from {current_branch}"
                )
                synced.append(branch)
                if not quiet:
                    success(branch, prefix="  ✓")
            except subprocess.CalledProcessError:
                # Already has same content
                if not quiet:
                    muted(f"  {branch} (unchanged)")

        except subprocess.CalledProcessError:
            if not quiet:
                error(f"{branch} (failed)", prefix="  ✗")

    # Return to original branch
    try:
        dotfiles._git.run("checkout", current_branch)
    except subprocess.CalledProcessError:
        pass

    if synced and not quiet:
        muted(f"  Synced to {len(synced)} branch(es)")


def _commit_files_individually(
    dotfiles,
    changed_files: List[str],
    user_message: Optional[str],
    quiet: bool,
) -> bool:
    """Commit each changed file individually.

    This enables clean config sync (config commit is isolated) and
    atomic rollback of individual files.

    Args:
        dotfiles: DotfilesManager instance
        changed_files: List of changed file paths
        user_message: Optional user-provided message to append
        quiet: Suppress output

    Returns:
        True if all commits succeeded
    """
    for filepath in changed_files:
        try:
            dotfiles._git.run("add", filepath)

            # Build commit message: "Update <file>" or "Update <file> -- msg"
            if user_message:
                commit_msg = f"Update {filepath} -- {user_message}"
            else:
                commit_msg = f"Update {filepath}"

            dotfiles._git.run("commit", "-m", commit_msg)

            if not quiet:
                muted(f"  ✓ {filepath}")

        except subprocess.CalledProcessError as e:
            if not quiet:
                error(f"Failed to commit {filepath}: {e}")
            return False

    return True


def do_save(
    message: Optional[str] = None,
    quiet: bool = False,
    scheduled: bool = False,
    dry_run: bool = False,
    skip_secret_check: bool = False,
) -> bool:
    """Internal save logic. Returns True on success.

    Saves changes locally first, then tries to sync to remote.
    Does not fail if remote sync fails (offline-friendly).
    """
    config = get_config()

    dotfiles = get_dotfiles_manager(config)
    if not dotfiles:
        if not quiet:
            error("No dotfiles configured. Run 'freckle init' first.")
        return False

    dotfiles_dir = get_dotfiles_dir(config)

    if not dotfiles_dir.exists():
        if not quiet:
            error("Dotfiles repository not found. Run 'freckle init' first.")
        return False

    report = dotfiles.get_detailed_status()

    if not report["has_local_changes"] and not report.get("is_ahead", False):
        if not quiet:
            success("Nothing to save - already up-to-date.")
        return True

    changed_files = report.get("changed_files", [])

    # Check for secrets in changed files
    if changed_files and not skip_secret_check:
        scanner = get_secret_scanner(config)
        secrets_found = scanner.scan_files(changed_files, env.home)

        if secrets_found:
            if not quiet:
                error(
                    f"Found potential secrets in {len(secrets_found)} file(s):"
                )
                plain_err("")
                for match in secrets_found:
                    plain_err(f"  {match.file}")
                    plain_err(f"    └─ {match.reason}")
                    if match.line:
                        plain_err(f"       (line {match.line})")

                plain_err("\nTo untrack: freckle untrack <file>")
                plain_err("To save anyway: freckle save --skip-secret-check")
            return False

    # Dry run - show what would happen
    if dry_run:
        plain("\n--- DRY RUN (no changes will be made) ---\n")
        if report["has_local_changes"]:
            plain("Would save the following files:")
            for f in changed_files:
                plain(f"  - {f}")
        if report.get("is_ahead", False):
            ahead = report.get("ahead_count", 0)
            plain(f"\nWould sync {ahead} change(s) to cloud.")
        elif report["has_local_changes"]:
            plain("\nWould sync to cloud.")
        plain("\n--- Dry Run Complete ---")
        return True

    if report["has_local_changes"] and not quiet:
        plain("Saving changed file(s):")

    # Commit each file individually (single-file commit discipline)
    # This enables clean config sync and atomic rollback
    config_changed = False
    if report["has_local_changes"]:
        # Commit config FIRST (so sync happens with latest config)
        if CONFIG_FILENAME in changed_files:
            config_files = [CONFIG_FILENAME]
            other_files = [f for f in changed_files if f != CONFIG_FILENAME]
            ordered_files = config_files + other_files
            config_changed = True
        else:
            ordered_files = changed_files

        success_commits = _commit_files_individually(
            dotfiles, ordered_files, message, quiet
        )

        if not success_commits:
            return False

        if not quiet:
            success(f"Saved {len(ordered_files)} file(s) locally")
            muted("  Run 'freckle push' to sync to cloud")

    # Sync config to all local branches if it was changed
    if config_changed:
        _sync_config_to_all_branches(dotfiles, quiet)

    return True


def save(
    message: Optional[str] = typer.Option(
        None, "-m", "--message", help="Custom message for this save"
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress output (for scripts/cron)"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", "-n", help="Show what would happen without acting"
    ),
    skip_secret_check: bool = typer.Option(
        False,
        "--skip-secret-check",
        help="Save even if secrets are detected (not recommended)",
    ),
    scheduled: bool = typer.Option(
        False, "--scheduled", hidden=True, help="Mark as scheduled save"
    ),
):
    """Save local changes to your dotfiles.

    Commits changes locally with single-file commits. Each changed file
    gets its own commit. If config is changed, it's synced to all local
    branches.

    Note: This does NOT push to remote. Use 'freckle push' to sync to cloud.

    Examples:
        freckle save                    # Save all changes locally
        freckle save -m "add fzf"       # With message for each commit
        freckle save && freckle push    # Save and push to cloud
    """
    result = do_save(
        message=message,
        skip_secret_check=skip_secret_check,
        quiet=quiet,
        scheduled=scheduled,
        dry_run=dry_run,
    )
    if not result:
        raise typer.Exit(1)
