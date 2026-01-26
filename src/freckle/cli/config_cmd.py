"""Config management commands for freckle CLI."""

import subprocess

import typer

from .helpers import get_config, get_dotfiles_dir, get_dotfiles_manager


def register(app: typer.Typer) -> None:
    """Register config command with the app."""
    # Note: 'config' without subcommand opens the file (in files.py)
    # These are additional config management commands
    app.command(name="config-check")(config_check)
    app.command(name="config-propagate")(config_propagate)


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
        branch = profile.get("branch", name)

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
            "\nRun 'freckle config-propagate' to sync config to all branches."
        )
        raise typer.Exit(1)
    else:
        typer.echo("\n✓ Config is consistent across all branches.")


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
        branch = profile.get("branch", name)
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

    # Check for uncommitted changes
    try:
        result = dotfiles._git.run("status", "--porcelain")
        has_changes = bool(result.stdout.strip())
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
