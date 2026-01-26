"""Git convenience commands for freckle CLI (log, branch, diff)."""

import subprocess
from pathlib import Path
from typing import List, Optional

import typer

from ..utils import setup_logging
from .helpers import env, get_config, get_dotfiles_manager, get_dotfiles_dir


def register(app: typer.Typer) -> None:
    """Register git commands with the app."""
    app.command()(log)
    app.command()(branch)
    app.command()(diff)


def log(
    count: int = typer.Option(10, "-n", "--count", help="Number of commits to show"),
    oneline: bool = typer.Option(False, "--oneline", help="Compact one-line format"),
):
    """Show commit history of your dotfiles repository.
    
    Examples:
        freckle log              # Show last 10 commits
        freckle log -n 5         # Show last 5 commits
        freckle log --oneline    # Compact format
    """
    setup_logging()
    config = get_config()
    
    dotfiles = get_dotfiles_manager(config)
    if not dotfiles:
        typer.echo("Dotfiles not configured. Run 'freckle init' first.", err=True)
        raise typer.Exit(1)
    
    dotfiles_dir = get_dotfiles_dir(config)
    
    if not dotfiles_dir.exists():
        typer.echo("Dotfiles repository not found. Run 'freckle sync' first.", err=True)
        raise typer.Exit(1)
    
    try:
        if oneline:
            result = dotfiles._git("log", f"-{count}", "--oneline")
        else:
            result = dotfiles._git("log", f"-{count}", "--format=%C(yellow)%h%C(reset) - %C(green)%ar%C(reset) - %s")
        
        if result.stdout.strip():
            typer.echo(f"\nRecent commits (last {count}):\n")
            typer.echo(result.stdout)
        else:
            typer.echo("No commits yet.")
    except subprocess.CalledProcessError as e:
        typer.echo(f"Error: {e.stderr}", err=True)
        raise typer.Exit(1)


def branch(
    name: Optional[str] = typer.Argument(None, help="Branch name to switch to"),
    create: bool = typer.Option(False, "-c", "--create", help="Create a new branch"),
    list_all: bool = typer.Option(False, "-a", "--all", help="List all branches including remotes"),
):
    """Show or switch branches in your dotfiles repository.
    
    Examples:
        freckle branch              # List local branches
        freckle branch -a           # List all branches (including remote)
        freckle branch work         # Switch to 'work' branch
        freckle branch -c laptop    # Create and switch to 'laptop' branch
    """
    setup_logging()
    config = get_config()
    
    dotfiles = get_dotfiles_manager(config)
    if not dotfiles:
        typer.echo("Dotfiles not configured. Run 'freckle init' first.", err=True)
        raise typer.Exit(1)
    
    dotfiles_dir = get_dotfiles_dir(config)
    
    if not dotfiles_dir.exists():
        typer.echo("Dotfiles repository not found. Run 'freckle sync' first.", err=True)
        raise typer.Exit(1)
    
    try:
        if name:
            # Switch to or create branch
            if create:
                dotfiles._git("checkout", "-b", name)
                typer.echo(f"✓ Created and switched to branch '{name}'")
            else:
                dotfiles._git("checkout", name)
                typer.echo(f"✓ Switched to branch '{name}'")
        else:
            # List branches
            if list_all:
                result = dotfiles._git("branch", "-a")
            else:
                result = dotfiles._git("branch")
            
            if result.stdout.strip():
                typer.echo("\nBranches:\n")
                typer.echo(result.stdout)
            else:
                typer.echo("No branches found.")
    except subprocess.CalledProcessError as e:
        typer.echo(f"Error: {e.stderr.strip()}", err=True)
        raise typer.Exit(1)


def diff(
    files: Optional[List[str]] = typer.Argument(None, help="Specific files to diff"),
    staged: bool = typer.Option(False, "--staged", help="Show staged changes"),
):
    """Show uncommitted changes in your dotfiles.
    
    Examples:
        freckle diff              # Show all uncommitted changes
        freckle diff .zshrc       # Show changes to specific file
        freckle diff --staged     # Show staged changes
    """
    setup_logging()
    config = get_config()
    
    dotfiles = get_dotfiles_manager(config)
    if not dotfiles:
        typer.echo("Dotfiles not configured. Run 'freckle init' first.", err=True)
        raise typer.Exit(1)
    
    dotfiles_dir = get_dotfiles_dir(config)
    
    if not dotfiles_dir.exists():
        typer.echo("Dotfiles repository not found. Run 'freckle sync' first.", err=True)
        raise typer.Exit(1)
    
    try:
        args = ["diff", "--color=always"]
        if staged:
            args.append("--staged")
        
        if files:
            # Convert paths to home-relative
            for f in files:
                path = Path(f).expanduser()
                if not path.is_absolute():
                    path = Path.cwd() / path
                path = path.resolve()
                try:
                    relative = path.relative_to(env.home)
                    args.append(str(relative))
                except ValueError:
                    args.append(f)
        
        result = dotfiles._git(*args)
        
        if result.stdout.strip():
            typer.echo("\nChanges not yet backed up:\n")
            typer.echo(result.stdout)
        else:
            if staged:
                typer.echo("No staged changes.")
            else:
                typer.echo("No uncommitted changes.")
    except subprocess.CalledProcessError as e:
        typer.echo(f"Error: {e.stderr}", err=True)
        raise typer.Exit(1)
