"""Add, remove, and propagate file commands for freckle CLI."""

import subprocess
from pathlib import Path
from typing import List, Optional

import typer

from freckle.secrets import SecretScanner

from .helpers import env, get_config, get_dotfiles_dir, get_dotfiles_manager


def register(app: typer.Typer) -> None:
    """Register file commands with the app."""
    app.command()(add)
    app.command()(remove)
    app.command()(propagate)


def add(
    files: List[str] = typer.Argument(
        ..., help="Files to add to dotfiles tracking"
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Add files even if they appear to contain secrets",
    ),
):
    """Add files to be tracked in your dotfiles repository.

    Examples:
        freckle add .freckle.yaml
        freckle add .vimrc .bashrc
        freckle add .config/starship.toml
        freckle add ~/.config/nvim/init.lua

    After adding, run 'freckle backup' to commit and push.
    """

    if not files:
        typer.echo("Usage: freckle add <file> [file2] [file3] ...")
        raise typer.Exit(1)

    config = get_config()

    dotfiles = get_dotfiles_manager(config)
    if not dotfiles:
        typer.echo(
            "Dotfiles not configured. Run 'freckle init' first.", err=True
        )
        raise typer.Exit(1)

    dotfiles_dir = get_dotfiles_dir(config)

    if not dotfiles_dir.exists():
        typer.echo(
            "Dotfiles repository not found. Run 'freckle sync' first.",
            err=True,
        )
        raise typer.Exit(1)

    # Convert user-provided paths to paths relative to home directory
    home_relative_files = []
    for f in files:
        path = Path(f).expanduser()

        if not path.is_absolute():
            path = Path.cwd() / path

        path = path.resolve()

        try:
            relative = path.relative_to(env.home)
            home_relative_files.append(str(relative))
        except ValueError:
            typer.echo(f"File must be under home directory: {f}", err=True)
            continue

    if not home_relative_files:
        raise typer.Exit(1)

    # Check for secrets unless --force is used
    if not force:
        secrets_config = config.get("secrets", {})
        scanner = SecretScanner(
            extra_block=secrets_config.get("block", []),
            extra_allow=secrets_config.get("allow", []),
        )
        secrets_found = scanner.scan_files(home_relative_files, env.home)

        if secrets_found:
            typer.echo(
                f"✗ Blocked: {len(secrets_found)} file(s) appear to "
                "contain secrets:\n",
                err=True,
            )
            for match in secrets_found:
                typer.echo(f"  {match.file}", err=True)
                typer.echo(f"    └─ {match.reason}", err=True)
                if match.line:
                    typer.echo(f"       (line {match.line})", err=True)

            typer.echo(
                "\nSecrets should not be tracked in dotfiles.", err=True
            )
            typer.echo(
                "To override (not recommended): freckle add --force <files>",
                err=True,
            )
            raise typer.Exit(1)

    result = dotfiles.add_files(home_relative_files)

    if result["added"]:
        typer.echo(f"✓ Staged {len(result['added'])} file(s) for tracking:")
        for f in result["added"]:
            typer.echo(f"    + {f}")

    if result["skipped"]:
        typer.echo(f"\n⚠ Skipped {len(result['skipped'])} file(s):")
        for f in result["skipped"]:
            file_path = env.home / f
            if not file_path.exists():
                typer.echo(f"    - {f} (file not found)")
            else:
                typer.echo(f"    - {f} (failed to add)")

    if result["added"]:
        typer.echo("\nTo commit and push, run: freckle backup")
    else:
        raise typer.Exit(1)


def remove(
    files: List[str] = typer.Argument(..., help="Files to stop tracking"),
    delete: bool = typer.Option(
        False, "--delete", help="Also delete the file from home directory"
    ),
):
    """Stop tracking files in your dotfiles repository.

    By default, the file is kept in your home directory but removed from
    git tracking. Use --delete to also remove the file.

    Examples:
        freckle remove .bashrc              # Stop tracking, keep file
        freckle remove .old-config --delete # Stop tracking and delete

    After removing, run 'freckle backup' to commit and push.
    """

    if not files:
        typer.echo("Usage: freckle remove <file> [file2] ...")
        raise typer.Exit(1)

    config = get_config()

    dotfiles = get_dotfiles_manager(config)
    if not dotfiles:
        typer.echo(
            "Dotfiles not configured. Run 'freckle init' first.", err=True
        )
        raise typer.Exit(1)

    dotfiles_dir = get_dotfiles_dir(config)

    if not dotfiles_dir.exists():
        typer.echo(
            "Dotfiles repository not found. Run 'freckle sync' first.",
            err=True,
        )
        raise typer.Exit(1)

    # Convert user-provided paths to paths relative to home directory
    home_relative_files = []
    for f in files:
        path = Path(f).expanduser()

        if not path.is_absolute():
            # Could be relative to cwd or already home-relative
            cwd_path = Path.cwd() / path
            home_path = env.home / path

            if cwd_path.exists():
                path = cwd_path.resolve()
            elif home_path.exists():
                path = home_path.resolve()
            else:
                # Assume it's home-relative even if file doesn't exist
                path = home_path.resolve()

        try:
            relative = path.relative_to(env.home)
            home_relative_files.append(str(relative))
        except ValueError:
            typer.echo(f"File must be under home directory: {f}", err=True)
            continue

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
            typer.echo(
                f"✓ Stopped tracking and deleted {len(removed)} file(s):"
            )
        else:
            typer.echo(f"✓ Stopped tracking {len(removed)} file(s):")
        for f in removed:
            if delete:
                typer.echo(f"    - {f} (deleted)")
            else:
                typer.echo(f"    - {f} (kept in ~/)")

    if skipped:
        typer.echo(f"\n⚠ Failed to remove {len(skipped)} file(s):")
        for f, err in skipped:
            typer.echo(f"    - {f}: {err}")

    if removed:
        typer.echo("\nTo commit this change, run: freckle backup")
    else:
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

    # Normalize file path to be relative to home
    file_path = Path(file).expanduser()
    if not file_path.is_absolute():
        # Check if it exists relative to cwd or home
        cwd_path = Path.cwd() / file_path
        home_path = env.home / file_path
        if cwd_path.exists():
            file_path = cwd_path.resolve()
        elif home_path.exists():
            file_path = home_path.resolve()
        else:
            file_path = home_path.resolve()

    try:
        relative_path = str(file_path.relative_to(env.home))
    except ValueError:
        typer.echo(f"File must be under home directory: {file}", err=True)
        raise typer.Exit(1)

    # Get current branch
    try:
        result = dotfiles._git.run("rev-parse", "--abbrev-ref", "HEAD")
        current_branch = result.stdout.strip()
    except subprocess.CalledProcessError:
        typer.echo("Failed to get current branch.", err=True)
        raise typer.Exit(1)

    # Get file content from current branch
    try:
        git_path = f"{current_branch}:{relative_path}"
        result = dotfiles._git.run("show", git_path)
        file_content = result.stdout
    except subprocess.CalledProcessError:
        typer.echo(
            f"File not found in current branch: {relative_path}", err=True
        )
        raise typer.Exit(1)

    # Determine target branches
    if to:
        # Validate specified branches exist as profiles
        branches_to_update = []
        for branch in to:
            if branch not in profiles:
                typer.echo(
                    f"Warning: '{branch}' is not a profile branch", err=True
                )
            if branch != current_branch:
                branches_to_update.append(branch)
    else:
        # All profile branches except current
        branches_to_update = [
            name for name in profiles if name != current_branch
        ]

    if not branches_to_update:
        typer.echo("No other branches to update.")
        return

    n = len(branches_to_update)
    typer.echo(
        f"Propagating {relative_path} from '{current_branch}' "
        f"to {n} branch(es):"
    )
    for branch in branches_to_update:
        typer.echo(f"  - {branch}")

    if dry_run:
        typer.echo("\n--- Dry run, no changes made ---")
        return

    if not force:
        if not typer.confirm("\nProceed?"):
            typer.echo("Cancelled.")
            return

    typer.echo("")

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
        typer.echo("Stashing local changes...")
        try:
            dotfiles._git.run("stash", "push", "-m", "freckle propagate")
            stashed = True
        except subprocess.CalledProcessError:
            typer.echo("Failed to stash changes.", err=True)
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
                typer.echo(f"  ✓ {branch}")

            except subprocess.CalledProcessError as e:
                failed.append((branch, str(e)))
                typer.echo(f"  ✗ {branch} - failed")

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
        typer.echo(f"✓ Updated {len(updated)} branch(es).")

        if push:
            typer.echo("\nPushing changes...")
            for branch in updated:
                try:
                    dotfiles._git.run("push", "origin", branch)
                    typer.echo(f"  ✓ Pushed {branch}")
                except subprocess.CalledProcessError:
                    typer.echo(f"  ✗ Failed to push {branch}")
        else:
            typer.echo("\nTo push changes:")
            typer.echo(f"  git push origin {' '.join(updated)}")

    if failed:
        typer.echo(f"\n✗ Failed to update {len(failed)} branch(es).")
        raise typer.Exit(1)
