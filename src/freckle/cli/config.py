"""Config management commands for freckle CLI."""

import os
import shutil
import subprocess

import typer

from .helpers import env, get_config, get_dotfiles_dir, get_dotfiles_manager

# Create config sub-app
config_app = typer.Typer(
    name="config",
    help="Manage freckle configuration.",
    no_args_is_help=False,  # Allow 'freckle config' to run edit
)


def register(app: typer.Typer) -> None:
    """Register config command group with the app."""
    app.add_typer(config_app, name="config")


@config_app.callback(invoke_without_command=True)
def config_callback(ctx: typer.Context):
    """Open the freckle configuration file in your editor.

    Without subcommands, opens config in $EDITOR.
    Use 'freckle config check' or 'freckle config propagate' for more.
    """
    # Only run edit if no subcommand was invoked
    if ctx.invoked_subcommand is None:
        config_edit()


def config_edit():
    """Open the freckle configuration file in your editor."""
    config_path = env.home / ".freckle.yaml"

    if not config_path.exists():
        typer.echo(f"Config file not found: {config_path}")
        typer.echo("Run 'freckle init' to create one.")
        raise typer.Exit(1)

    # Try $EDITOR or $VISUAL first
    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL")

    if editor:
        try:
            subprocess.run([editor, str(config_path)], check=True)
            return
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass  # Fall through to platform defaults

    # Platform-specific fallbacks
    is_mac = env.os_info.get("system") == "Darwin"

    if is_mac:
        subprocess.run(["open", "-t", str(config_path)], check=True)
    else:
        if shutil.which("xdg-open"):
            subprocess.run(["xdg-open", str(config_path)], check=True)
        elif shutil.which("nano"):
            subprocess.run(["nano", str(config_path)], check=True)
        elif shutil.which("vi"):
            subprocess.run(["vi", str(config_path)], check=True)
        else:
            typer.echo("Could not find an editor. Config file is at:")
            typer.echo(f"  {config_path}")
            raise typer.Exit(1)


@config_app.command(name="check")
def config_check():
    """Check if .freckle.yaml is consistent across all profile branches.

    Compares the config file on the current branch to all other profile
    branches. Reports any differences.
    """
    config = get_config()
    profiles = config.get_profiles()

    if not profiles:
        typer.echo("No profiles configured.")
        return

    dotfiles = get_dotfiles_manager(config)
    if not dotfiles:
        typer.echo("Dotfiles not configured.", err=True)
        raise typer.Exit(1)

    dotfiles_dir = get_dotfiles_dir(config)
    if not dotfiles_dir.exists():
        typer.echo("Dotfiles repository not found.", err=True)
        raise typer.Exit(1)

    # Get current branch
    try:
        result = dotfiles._git.run("rev-parse", "--abbrev-ref", "HEAD")
        current_branch = result.stdout.strip()
    except subprocess.CalledProcessError:
        typer.echo("Failed to get current branch.", err=True)
        raise typer.Exit(1)

    # Get current config content
    try:
        result = dotfiles._git.run("show", f"{current_branch}:.freckle.yaml")
        current_content = result.stdout
    except subprocess.CalledProcessError:
        typer.echo(
            "No .freckle.yaml found on current branch.", err=True
        )
        raise typer.Exit(1)

    typer.echo("Checking .freckle.yaml consistency across branches...\n")

    consistent = []
    inconsistent = []

    for name, profile in profiles.items():
        branch = name  # Profile name = branch name

        if branch == current_branch:
            consistent.append((name, branch, "(current)"))
            continue

        try:
            result = dotfiles._git.run("show", f"{branch}:.freckle.yaml")
            other_content = result.stdout

            if other_content == current_content:
                consistent.append((name, branch, ""))
            else:
                inconsistent.append((name, branch))
        except subprocess.CalledProcessError:
            # Branch might not have .freckle.yaml yet
            inconsistent.append((name, branch))

    # Report results
    for name, branch, note in consistent:
        if note:
            typer.echo(f"  ✓ {name} ({branch}) {note}")
        else:
            typer.echo(f"  ✓ {name} ({branch})")

    for name, branch in inconsistent:
        typer.echo(f"  ✗ {name} ({branch}) - differs or missing")

    if inconsistent:
        typer.echo(
            "\nRun 'freckle config propagate' to sync config to all branches."
        )
        raise typer.Exit(1)
    else:
        typer.echo("\n✓ Config is consistent across all branches.")


@config_app.command(name="propagate")
def config_propagate(
    force: bool = typer.Option(
        False, "--force", "-f", help="Skip confirmation"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", "-n", help="Show what would happen"
    ),
):
    """Propagate .freckle.yaml to all profile branches.

    Copies the current branch's .freckle.yaml to all other profile branches,
    creating a commit on each.
    """
    config = get_config()
    profiles = config.get_profiles()

    if not profiles:
        typer.echo("No profiles configured.")
        return

    dotfiles = get_dotfiles_manager(config)
    if not dotfiles:
        typer.echo("Dotfiles not configured.", err=True)
        raise typer.Exit(1)

    dotfiles_dir = get_dotfiles_dir(config)
    if not dotfiles_dir.exists():
        typer.echo("Dotfiles repository not found.", err=True)
        raise typer.Exit(1)

    # Get current branch
    try:
        result = dotfiles._git.run("rev-parse", "--abbrev-ref", "HEAD")
        current_branch = result.stdout.strip()
    except subprocess.CalledProcessError:
        typer.echo("Failed to get current branch.", err=True)
        raise typer.Exit(1)

    # Get current config content
    try:
        result = dotfiles._git.run("show", f"{current_branch}:.freckle.yaml")
        current_content = result.stdout
    except subprocess.CalledProcessError:
        typer.echo(
            "No .freckle.yaml found on current branch.", err=True
        )
        raise typer.Exit(1)

    # Find branches to update
    branches_to_update = []
    for name, profile in profiles.items():
        branch = name  # Profile name = branch name
        if branch != current_branch:
            branches_to_update.append((name, branch))

    if not branches_to_update:
        typer.echo("No other branches to update.")
        return

    typer.echo(
        f"Will update .freckle.yaml on {len(branches_to_update)} branch(es):"
    )
    for name, branch in branches_to_update:
        typer.echo(f"  - {name} ({branch})")

    if dry_run:
        typer.echo("\n--- Dry run, no changes made ---")
        return

    if not force:
        if not typer.confirm("\nProceed?"):
            typer.echo("Cancelled.")
            return

    typer.echo("")

    # Check for uncommitted changes (only tracked files)
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
        typer.echo("Stashing local changes...")
        try:
            dotfiles._git.run(
                "stash", "push", "-m", "freckle config propagate"
            )
            stashed = True
        except subprocess.CalledProcessError:
            typer.echo("Failed to stash changes.", err=True)
            raise typer.Exit(1)

    updated = []
    failed = []

    try:
        for name, branch in branches_to_update:
            try:
                # Checkout branch
                dotfiles._git.run("checkout", branch)

                # Write config file
                config_path = dotfiles.work_tree / ".freckle.yaml"
                config_path.write_text(current_content)

                # Stage and commit
                dotfiles._git.run("add", ".freckle.yaml")
                dotfiles._git.run(
                    "commit", "-m",
                    f"Sync .freckle.yaml from {current_branch}"
                )

                updated.append((name, branch))
                typer.echo(f"  ✓ {name} ({branch})")

            except subprocess.CalledProcessError as e:
                failed.append((name, branch, str(e)))
                typer.echo(f"  ✗ {name} ({branch}) - failed")

    finally:
        # Return to original branch
        try:
            dotfiles._git.run("checkout", current_branch)
        except subprocess.CalledProcessError:
            typer.echo(
                f"Warning: failed to return to {current_branch}", err=True
            )

        # Restore stashed changes
        if stashed:
            try:
                dotfiles._git.run("stash", "pop")
            except subprocess.CalledProcessError:
                typer.echo("Warning: failed to restore stashed changes")

    typer.echo("")

    if updated:
        typer.echo(f"Updated {len(updated)} branch(es).")
        typer.echo("\nTo push changes:")
        branch_names = [b for _, b in updated]
        typer.echo(f"  git push origin {' '.join(branch_names)}")

    if failed:
        typer.echo(f"\nFailed to update {len(failed)} branch(es).")
        raise typer.Exit(1)
