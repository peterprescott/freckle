"""Add and remove file commands for freckle CLI."""

import subprocess
from pathlib import Path
from typing import List

import typer

from ..utils import setup_logging
from .helpers import env, get_config, get_dotfiles_manager, get_dotfiles_dir


def register(app: typer.Typer) -> None:
    """Register file commands with the app."""
    app.command()(add)
    app.command()(remove)


def add(
    files: List[str] = typer.Argument(..., help="Files to add to dotfiles tracking"),
):
    """Add files to be tracked in your dotfiles repository.
    
    Examples:
        freckle add .freckle.yaml
        freckle add .vimrc .bashrc
        freckle add .config/starship.toml
        freckle add ~/.config/nvim/init.lua
    
    After adding, run 'freckle backup' to commit and push.
    """
    setup_logging()
    
    if not files:
        typer.echo("Usage: freckle add <file> [file2] [file3] ...")
        raise typer.Exit(1)
    
    config = get_config()
    
    dotfiles = get_dotfiles_manager(config)
    if not dotfiles:
        typer.echo("Dotfiles not configured. Run 'freckle init' first.", err=True)
        raise typer.Exit(1)
    
    dotfiles_dir = get_dotfiles_dir(config)
    
    if not dotfiles_dir.exists():
        typer.echo("Dotfiles repository not found. Run 'freckle sync' first.", err=True)
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
    delete: bool = typer.Option(False, "--delete", help="Also delete the file from home directory"),
):
    """Stop tracking files in your dotfiles repository.
    
    By default, the file is kept in your home directory but removed from
    git tracking. Use --delete to also remove the file.
    
    Examples:
        freckle remove .bashrc              # Stop tracking, keep file
        freckle remove .old-config --delete # Stop tracking and delete
    
    After removing, run 'freckle backup' to commit and push.
    """
    setup_logging()
    
    if not files:
        typer.echo("Usage: freckle remove <file> [file2] ...")
        raise typer.Exit(1)
    
    config = get_config()
    
    dotfiles = get_dotfiles_manager(config)
    if not dotfiles:
        typer.echo("Dotfiles not configured. Run 'freckle init' first.", err=True)
        raise typer.Exit(1)
    
    dotfiles_dir = get_dotfiles_dir(config)
    
    if not dotfiles_dir.exists():
        typer.echo("Dotfiles repository not found. Run 'freckle sync' first.", err=True)
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
                dotfiles._git("rm", f)
            else:
                # Remove from git but keep file
                dotfiles._git("rm", "--cached", f)
            removed.append(f)
        except subprocess.CalledProcessError as e:
            skipped.append((f, str(e)))
    
    if removed:
        if delete:
            typer.echo(f"✓ Stopped tracking and deleted {len(removed)} file(s):")
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
