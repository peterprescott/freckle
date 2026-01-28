"""Save command for committing and pushing dotfiles changes."""

import subprocess
from typing import List, Optional

import typer

from ..secrets import SecretScanner
from .helpers import (
    CONFIG_FILENAME,
    env,
    get_config,
    get_dotfiles_dir,
    get_dotfiles_manager,
)


def register(app: typer.Typer) -> None:
    """Register save command with the app."""
    app.command()(save)


def _auto_propagate_config(config, dotfiles, offline: bool, quiet: bool):
    """Auto-propagate config to other profile branches after save."""
    profiles = config.get_profiles()
    if len(profiles) <= 1:
        return  # No other branches to sync

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

    # Find branches to update
    branches_to_update = [
        name for name in profiles.keys() if name != current_branch
    ]

    if not branches_to_update:
        return

    if not quiet:
        typer.echo(f"\nSyncing {CONFIG_FILENAME} to other branches...")

    updated = []
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
                updated.append(branch)
                if not quiet:
                    typer.echo(f"  ✓ {branch}")
            except subprocess.CalledProcessError:
                # Already has same content
                if not quiet:
                    typer.echo(f"  ✓ {branch} (already synced)")

        except subprocess.CalledProcessError:
            if not quiet:
                typer.echo(f"  ✗ {branch} (failed)")

    # Return to original branch
    try:
        dotfiles._git.run("checkout", current_branch)
    except subprocess.CalledProcessError:
        pass

    # Push updated branches if online
    if updated and not offline:
        try:
            dotfiles._git.run_bare(
                "push", "origin", *updated, check=True, timeout=60
            )
            if not quiet:
                typer.echo(f"  Pushed {len(updated)} branch(es)")
        except subprocess.CalledProcessError:
            if not quiet:
                typer.echo("  ⚠ Could not push synced branches (offline?)")


def _build_commit_message(
    prefix: str, changed_files: List[str], platform: str
) -> str:
    """Build a descriptive commit message including changed files."""
    lines = [f"{prefix} from {platform}"]

    if changed_files:
        lines.append("")
        lines.append("Changed files:")
        for f in changed_files:
            lines.append(f"  - {f}")

    return "\n".join(lines)


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
            typer.echo(
                "No dotfiles repository configured. Run 'freckle init' first.",
                err=True,
            )
        return False

    dotfiles_dir = get_dotfiles_dir(config)

    if not dotfiles_dir.exists():
        if not quiet:
            typer.echo(
                "Dotfiles repository not found. Run 'freckle init' first.",
                err=True,
            )
        return False

    report = dotfiles.get_detailed_status()

    if not report["has_local_changes"] and not report.get("is_ahead", False):
        if not quiet:
            typer.echo("✓ Nothing to save - already up-to-date.")
        return True

    changed_files = report.get("changed_files", [])

    # Check for secrets in changed files
    if changed_files and not skip_secret_check:
        secrets_config = config.get("secrets", {})
        scanner = SecretScanner(
            extra_block=secrets_config.get("block", []),
            extra_allow=secrets_config.get("allow", []),
        )
        secrets_found = scanner.scan_files(changed_files, env.home)

        if secrets_found:
            if not quiet:
                typer.echo(
                    f"✗ Found potential secrets in {len(secrets_found)} "
                    "file(s):\n",
                    err=True,
                )
                for match in secrets_found:
                    typer.echo(f"  {match.file}", err=True)
                    typer.echo(f"    └─ {match.reason}", err=True)
                    if match.line:
                        typer.echo(f"       (line {match.line})", err=True)

                typer.echo(
                    "\nTo untrack: freckle untrack <file>",
                    err=True,
                )
                typer.echo(
                    "To save anyway: freckle save --skip-secret-check",
                    err=True,
                )
            return False

    # Dry run - show what would happen
    if dry_run:
        typer.echo("\n--- DRY RUN (no changes will be made) ---\n")
        if report["has_local_changes"]:
            typer.echo("Would save the following files:")
            for f in changed_files:
                typer.echo(f"  - {f}")
        if report.get("is_ahead", False):
            ahead = report.get("ahead_count", 0)
            typer.echo(f"\nWould sync {ahead} change(s) to cloud.")
        elif report["has_local_changes"]:
            typer.echo("\nWould sync to cloud.")
        typer.echo("\n--- Dry Run Complete ---")
        return True

    if report["has_local_changes"] and not quiet:
        typer.echo("Saving changed file(s):")
        for f in changed_files:
            typer.echo(f"  - {f}")

    # Build commit message
    if message:
        commit_msg = message
    else:
        prefix = "Scheduled save" if scheduled else "Save"
        commit_msg = _build_commit_message(
            prefix, changed_files, env.os_info["pretty_name"]
        )

    # First, commit locally (this always works)
    if report["has_local_changes"]:
        try:
            dotfiles._git.run("add", "-A")
            dotfiles._git.run("commit", "-m", commit_msg)
            if not quiet:
                typer.echo("✓ Saved locally")
        except Exception as e:
            if not quiet:
                typer.echo(f"✗ Failed to save: {e}", err=True)
            return False

    # Then, try to push (may fail if offline)
    offline = False
    try:
        result = dotfiles.push()
        if result.get("success"):
            if not quiet:
                typer.echo("✓ Synced to cloud")
        else:
            offline = True
            if not quiet:
                typer.echo("⚠ Could not sync to cloud (offline?)")
                typer.echo("  Run 'freckle save' again when online")
    except Exception:
        offline = True
        if not quiet:
            typer.echo("⚠ Could not sync to cloud (offline?)")
            typer.echo("  Run 'freckle save' again when online")

    # Auto-propagate config if it was changed
    if CONFIG_FILENAME in changed_files:
        _auto_propagate_config(config, dotfiles, offline, quiet)

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

    Saves any changes you've made to your dotfiles. Works offline - changes
    are saved locally first, then synced to the cloud when possible.

    Examples:
        freckle save                    # Save all changes
        freckle save -m "Updated zshrc" # With custom message
    """
    success = do_save(
        message=message,
        skip_secret_check=skip_secret_check,
        quiet=quiet,
        scheduled=scheduled,
        dry_run=dry_run,
    )
    if not success:
        raise typer.Exit(1)
