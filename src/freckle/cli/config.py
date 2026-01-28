"""Config management commands for freckle CLI."""

import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import List

import typer

from .helpers import (
    CONFIG_FILENAME,
    CONFIG_PATH,
    env,
    get_config,
    get_dotfiles_dir,
    get_dotfiles_manager,
)

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
    if not CONFIG_PATH.exists():
        typer.echo(f"Config file not found: {CONFIG_PATH}")
        typer.echo("Run 'freckle init' to create one.")
        raise typer.Exit(1)

    open_in_editor([CONFIG_PATH])


def open_in_editor(files: List[Path]) -> None:
    """Open one or more files in the user's editor."""
    if not files:
        typer.echo("No files to open.")
        raise typer.Exit(1)

    # Convert to strings
    file_args = [str(f) for f in files]

    # Try $EDITOR or $VISUAL first
    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL")

    if editor:
        try:
            subprocess.run([editor, *file_args], check=True)
            return
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass  # Fall through to platform defaults

    # Platform-specific fallbacks
    is_mac = platform.system() == "Darwin"

    if is_mac:
        # -W waits for the app to close, -t opens in default text editor
        subprocess.run(["open", "-W", "-t", *file_args], check=True)
    else:
        if shutil.which("xdg-open"):
            # xdg-open only handles one file at a time
            for f in file_args:
                subprocess.run(["xdg-open", f], check=True)
        elif shutil.which("nano"):
            subprocess.run(["nano", *file_args], check=True)
        elif shutil.which("vi"):
            subprocess.run(["vi", *file_args], check=True)
        else:
            typer.echo("Could not find an editor. Files are at:")
            for f in file_args:
                typer.echo(f"  {f}")
            raise typer.Exit(1)


def get_tool_config_files(tool_name: str) -> List[Path]:
    """Get the config file paths for a tool from .freckle.yaml."""
    config = get_config()
    tools_config = config.data.get("tools", {})

    # Special case: "freckle" refers to the freckle config itself
    if tool_name == "freckle":
        return [CONFIG_PATH] if CONFIG_PATH.exists() else []

    if tool_name not in tools_config:
        return []

    tool_data = tools_config[tool_name]
    config_files = tool_data.get("config", [])

    if not config_files:
        return []

    # Expand paths and check existence
    result = []
    for cfg in config_files:
        path = Path(cfg).expanduser()
        if not path.is_absolute():
            path = env.home / cfg
        result.append(path)

    return result


@config_app.command(name="open")
def config_open(
    tool_name: str = typer.Argument(
        ...,
        help="Tool name to open config for (e.g., 'nvim', 'zsh', 'tmux')",
    ),
):
    """Open a tool's config file(s) in your editor.

    Looks up the tool's config files from .freckle.yaml and opens them.

    Examples:
        freckle config open nvim    # Open nvim config
        freckle config open zsh     # Open zsh config (.zshrc etc)
        freckle config open freckle # Open the freckle config itself
    """
    files = get_tool_config_files(tool_name)

    if not files:
        typer.echo(f"No config files found for tool: {tool_name}", err=True)
        typer.echo("\nEither the tool is not defined in .freckle.yaml,")
        typer.echo("or it has no 'config' section.")
        typer.echo("\nTo add config files, edit .freckle.yaml:")
        typer.echo("  tools:")
        typer.echo(f"    {tool_name}:")
        typer.echo("      config:")
        typer.echo(f"        - ~/.config/{tool_name}/config")
        raise typer.Exit(1)

    # Filter to existing files
    existing = [f for f in files if f.exists()]
    missing = [f for f in files if not f.exists()]

    if missing:
        for f in missing:
            msg = f"Note: {f} does not exist"
            typer.echo(typer.style(msg, fg=typer.colors.YELLOW))

    if not existing:
        typer.echo("None of the config files exist yet.", err=True)
        typer.echo("\nExpected files:")
        for f in files:
            typer.echo(f"  {f}")
        raise typer.Exit(1)

    # Open existing files
    if len(existing) == 1:
        typer.echo(f"Opening {existing[0]}")
    else:
        typer.echo(f"Opening {len(existing)} config file(s) for {tool_name}")

    open_in_editor(existing)


@config_app.command(name="check")
def config_check():
    """Check if config is consistent across all profile branches.

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
        git_path = f"{current_branch}:{CONFIG_FILENAME}"
        result = dotfiles._git.run("show", git_path)
        current_content = result.stdout
    except subprocess.CalledProcessError:
        typer.echo(
            f"No {CONFIG_FILENAME} found on current branch.", err=True
        )
        raise typer.Exit(1)

    typer.echo(f"Checking {CONFIG_FILENAME} consistency...\n")

    consistent = []
    inconsistent = []

    for name, profile in profiles.items():
        branch = name  # Profile name = branch name

        if branch == current_branch:
            consistent.append((name, branch, "(current)"))
            continue

        try:
            result = dotfiles._git.run("show", f"{branch}:{CONFIG_FILENAME}")
            other_content = result.stdout

            if other_content == current_content:
                consistent.append((name, branch, ""))
            else:
                inconsistent.append((name, branch))
        except subprocess.CalledProcessError:
            # Branch might not have config file yet
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
    """Propagate config to all profile branches.

    Copies the current branch's config to all other profile branches,
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
        git_path = f"{current_branch}:{CONFIG_FILENAME}"
        result = dotfiles._git.run("show", git_path)
        current_content = result.stdout
    except subprocess.CalledProcessError:
        typer.echo(
            f"No {CONFIG_FILENAME} found on current branch.", err=True
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

    n = len(branches_to_update)
    typer.echo(f"Will update {CONFIG_FILENAME} on {n} branch(es):")
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
                target_config = dotfiles.work_tree / CONFIG_FILENAME
                target_config.write_text(current_content)

                # Stage and commit
                dotfiles._git.run("add", CONFIG_FILENAME)
                dotfiles._git.run(
                    "commit", "-m",
                    f"Sync {CONFIG_FILENAME} from {current_branch}"
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
