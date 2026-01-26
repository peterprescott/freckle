"""Command-line interface for freckle - keep track of all your dot(file)s."""

import logging
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional

import typer
import yaml

from .config import Config
from .dotfiles import DotfilesManager
from .environment import Environment
from .managers.git import GitManager
from .managers.nvim import NvimManager
from .managers.tmux import TmuxManager
from .managers.zsh import ZshManager
from .system import SystemPackageManager
from .utils import (
    get_version,
    setup_logging,
    validate_git_url,
    verify_git_url_accessible,
)

# Create the Typer app
app = typer.Typer(
    name="freckle",
    help="Keep track of all your dot(file)s. A dotfiles manager with tool installation.",
    add_completion=True,
    no_args_is_help=True,
)

# Global state
env = Environment()
logger = logging.getLogger(__name__)


def _get_config() -> Config:
    """Load config from ~/.freckle.yaml."""
    config_path = env.home / ".freckle.yaml"
    return Config(config_path, env=env)


def _get_dotfiles_manager(config: Config) -> Optional[DotfilesManager]:
    """Create a DotfilesManager from config."""
    repo_url = config.get("dotfiles.repo_url")
    if not repo_url:
        return None
    
    dotfiles_dir = Path(config.get("dotfiles.dir")).expanduser()
    if not dotfiles_dir.is_absolute():
        dotfiles_dir = env.home / dotfiles_dir
    branch = config.get("dotfiles.branch")
    
    return DotfilesManager(repo_url, dotfiles_dir, env.home, branch)


def _get_tool_managers(pkg_mgr: SystemPackageManager) -> list:
    """Create all tool managers."""
    return [
        GitManager(env, pkg_mgr),
        ZshManager(env, pkg_mgr),
        TmuxManager(env, pkg_mgr),
        NvimManager(env, pkg_mgr)
    ]


@app.command()
def init(
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing configuration")
):
    """Initialize configuration and set up dotfiles repository.
    
    Offers two modes:
    1. Clone an existing dotfiles repository
    2. Create a new dotfiles repository from scratch
    """
    setup_logging()
    config_path = env.home / ".freckle.yaml"
    
    if config_path.exists() and not force:
        typer.echo(f"Config file already exists at {config_path}. Use --force to overwrite.", err=True)
        raise typer.Exit(1)

    typer.echo("--- freckle Initialization ---\n")
    
    # Ask if they have an existing repo
    choice = typer.prompt("Do you have an existing dotfiles repository? [y/N]", default="n").strip().lower()
    
    if choice in ["y", "yes"]:
        _init_clone_existing(config_path)
    else:
        _init_create_new(config_path)


def _init_clone_existing(config_path: Path) -> None:
    """Initialize by cloning an existing dotfiles repo."""
    typer.echo("\n--- Clone Existing Repository ---\n")
    
    # Get and validate repository URL
    while True:
        repo_url = typer.prompt("Enter your dotfiles repository URL").strip()
        
        if not repo_url:
            typer.echo("  Repository URL is required.")
            continue
        
        if not validate_git_url(repo_url):
            typer.echo("  Invalid URL format. Please enter a valid git URL.")
            typer.echo("  Examples: https://github.com/user/repo.git")
            typer.echo("            git@github.com:user/repo.git")
            continue
        
        # Try to verify the URL is accessible
        typer.echo("  Verifying repository access...")
        accessible, error = verify_git_url_accessible(repo_url)
        if not accessible:
            typer.echo(f"  Warning: Could not access repository: {error}")
            confirm = typer.prompt("  Continue anyway? [y/N]", default="n").strip().lower()
            if confirm not in ["y", "yes"]:
                continue
        else:
            typer.echo("  ✓ Repository accessible")
        
        break
    
    branch = typer.prompt("Enter your preferred branch", default="main").strip().lower()
    dotfiles_dir = typer.prompt("Enter directory for bare repo", default=".dotfiles").strip()

    config_data = {
        "dotfiles": {
            "repo_url": repo_url,
            "branch": branch,
            "dir": dotfiles_dir
        },
        "modules": ["dotfiles", "zsh", "tmux", "nvim"]
    }

    with open(config_path, "w") as f:
        yaml.dump(config_data, f, default_flow_style=False)
    
    logger.info(f"Created configuration at {config_path}")
    typer.echo("\n✓ Configuration saved! Run 'freckle sync' to clone and set up your dotfiles.")


def _init_create_new(config_path: Path) -> None:
    """Initialize by creating a new dotfiles repo."""
    typer.echo("\n--- Create New Dotfiles Repository ---\n")
    
    repo_url = ""
    
    # Check if gh CLI is available
    has_gh = shutil.which("gh") is not None
    
    if has_gh:
        typer.echo("GitHub CLI detected. Create a new repo on GitHub?")
        create_gh = typer.prompt("Create repo with 'gh repo create'? [Y/n]", default="y").strip().lower()
        
        if create_gh not in ["n", "no"]:
            repo_name = typer.prompt("Repository name", default="dotfiles").strip()
            private = typer.prompt("Make it private? [Y/n]", default="y").strip().lower()
            visibility = "--private" if private not in ["n", "no"] else "--public"
            
            typer.echo(f"\n  Creating {repo_name} on GitHub...")
            try:
                result = subprocess.run(
                    ["gh", "repo", "create", repo_name, visibility, "--confirm"],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                if result.returncode == 0:
                    repo_url = result.stdout.strip()
                    if not repo_url:
                        user_result = subprocess.run(
                            ["gh", "api", "user", "-q", ".login"],
                            capture_output=True, text=True
                        )
                        if user_result.returncode == 0:
                            username = user_result.stdout.strip()
                            repo_url = f"https://github.com/{username}/{repo_name}.git"
                    typer.echo(f"  ✓ Created: {repo_url}")
                else:
                    typer.echo(f"  ✗ Failed: {result.stderr.strip()}")
                    typer.echo("  Continuing without remote.")
            except Exception as e:
                typer.echo(f"  ✗ Error: {e}")
                typer.echo("  Continuing without remote.")
    
    # If we don't have a URL yet, ask for one
    if not repo_url:
        if not has_gh:
            typer.echo("To sync across machines, you'll need a remote repository.")
            typer.echo("Create one on GitHub/GitLab, then enter the URL here.")
            typer.echo("Or leave blank to set up locally only.\n")
        else:
            typer.echo("\nEnter repository URL, or blank to skip:\n")
        
        while True:
            url_input = typer.prompt("Repository URL (or blank)", default="").strip()
            
            if not url_input:
                break
            
            if not validate_git_url(url_input):
                typer.echo("  Warning: URL format looks unusual.")
            
            typer.echo("  Checking repository access...")
            accessible, error = verify_git_url_accessible(url_input)
            if not accessible:
                typer.echo(f"  ✗ Cannot access repository: {error}")
                retry = typer.prompt("  Try a different URL? [Y/n]", default="y").strip().lower()
                if retry in ["n", "no"]:
                    break
                continue
            else:
                typer.echo("  ✓ Repository accessible")
                repo_url = url_input
                break
    
    branch = typer.prompt("Enter branch name", default="main").strip().lower()
    dotfiles_dir = typer.prompt("Enter directory for bare repo", default=".dotfiles").strip()
    
    # Ask which files to track initially
    typer.echo("\nWhich dotfiles do you want to track? (Enter comma-separated list)")
    typer.echo("Examples: .zshrc, .bashrc, .gitconfig, .tmux.conf, .config/nvim")
    typer.echo("Or press Enter for common defaults: .freckle.yaml, .zshrc, .gitconfig, .tmux.conf\n")
    
    files_input = typer.prompt("Files to track", default="").strip()
    if files_input:
        initial_files = [f.strip() for f in files_input.split(",") if f.strip()]
        if ".freckle.yaml" not in initial_files:
            initial_files.insert(0, ".freckle.yaml")
    else:
        initial_files = [".freckle.yaml", ".zshrc", ".gitconfig", ".tmux.conf"]
    
    # Check if dotfiles directory already exists
    dotfiles_path = Path(dotfiles_dir).expanduser()
    if not dotfiles_path.is_absolute():
        dotfiles_path = env.home / dotfiles_path
    if dotfiles_path.exists():
        typer.echo(f"\n⚠ Directory already exists: {dotfiles_path}")
        choice = typer.prompt("Remove it and start fresh? [y/N]", default="n").strip().lower()
        if choice in ["y", "yes"]:
            shutil.rmtree(dotfiles_path)
            typer.echo(f"  Removed {dotfiles_path}")
        else:
            typer.echo("  Aborting. Remove the directory manually or choose a different location.")
            raise typer.Exit(1)
    
    # Save config FIRST so it can be included in the initial commit
    config_data = {
        "dotfiles": {
            "repo_url": repo_url or f"file://{dotfiles_path}",
            "branch": branch,
            "dir": dotfiles_dir
        },
        "modules": ["dotfiles", "zsh", "tmux", "nvim"]
    }

    with open(config_path, "w") as f:
        yaml.dump(config_data, f, default_flow_style=False)
    
    logger.info(f"Created configuration at {config_path}")
    
    # Check which files exist
    all_files_to_track = []
    for f in initial_files:
        path = env.home / f
        if path.exists():
            all_files_to_track.append(f)
        else:
            typer.echo(f"  Note: {f} doesn't exist yet, skipping")
    
    if not all_files_to_track:
        typer.echo("\nNo existing files to track. You can add files later with:")
        typer.echo(f"  freckle add <file>")
    
    # Create the repo
    dotfiles = DotfilesManager(repo_url or "", dotfiles_path, env.home, branch)
    
    try:
        dotfiles.create_new(initial_files=all_files_to_track, remote_url=repo_url or None)
        typer.echo(f"\n✓ Created new dotfiles repository at {dotfiles_dir}")
        
        if all_files_to_track:
            typer.echo(f"✓ Tracking {len(all_files_to_track)} file(s): {', '.join(all_files_to_track)}")
    except Exception as e:
        logger.error(f"Failed to create repository: {e}")
        config_path.unlink(missing_ok=True)
        raise typer.Exit(1)
    
    if repo_url:
        typer.echo("\nNext steps:")
        typer.echo("  1. Run 'freckle backup' to push your dotfiles")
        typer.echo("  2. On other machines, run 'freckle init' and choose option 1")
    else:
        typer.echo("\nNext steps:")
        typer.echo("  1. Create a repo on GitHub/GitLab")
        typer.echo(f"  2. Add remote: git --git-dir={dotfiles_dir} remote add origin <url>")
        typer.echo(f"  3. Push: git --git-dir={dotfiles_dir} push -u origin main")


@app.command()
def sync(
    repo: Optional[str] = typer.Option(None, "--repo", "-r", help="Override dotfiles repository URL"),
    branch: Optional[str] = typer.Option(None, "--branch", "-b", help="Override git branch"),
):
    """Sync dotfiles and verify tool installations.
    
    Checks the current state of your dotfiles and reports any changes.
    If there are local changes, suggests 'freckle backup'.
    If remote has updates, suggests 'freckle update'.
    """
    setup_logging()
    config = _get_config()
    
    # Override from CLI
    if repo:
        if not validate_git_url(repo):
            typer.echo(f"Invalid repository URL: {repo}", err=True)
            raise typer.Exit(1)
        config.data["dotfiles"]["repo_url"] = repo
    if branch:
        config.data["dotfiles"]["branch"] = branch

    repo_url = config.get("dotfiles.repo_url")
    if not repo_url:
        typer.echo("No dotfiles repository URL found. Run 'freckle init' first.", err=True)
        raise typer.Exit(1)

    dotfiles_dir = Path(config.get("dotfiles.dir")).expanduser()
    if not dotfiles_dir.is_absolute():
        dotfiles_dir = env.home / dotfiles_dir
    branch_name = config.get("dotfiles.branch")
    work_tree = env.home
    enabled_modules = config.get("modules", [])

    is_first_run = not dotfiles_dir.exists()
    action_name = "Setup" if is_first_run else "Sync"
    
    typer.echo(f"\n--- freckle {action_name} ---")
    typer.echo(f"Platform: {env.os_info['pretty_name']}")
    
    pkg_mgr = SystemPackageManager(env)
    
    # Initialize managers
    dotfiles = DotfilesManager(repo_url, dotfiles_dir, work_tree, branch_name)
    tool_managers = _get_tool_managers(pkg_mgr)

    try:
        if "dotfiles" in enabled_modules:
            if is_first_run:
                typer.echo(f"[*] Initial setup of dotfiles from {repo_url}...")
                dotfiles.setup()
            else:
                report = dotfiles.get_detailed_status()
                
                if report.get("fetch_failed"):
                    typer.echo("⚠ Could not connect to remote (offline mode)")
                
                local_changes = report["has_local_changes"]
                is_behind = report.get("is_behind", False)
                is_ahead = report.get("is_ahead", False)

                if not local_changes and not is_behind and not is_ahead:
                    typer.echo("✓ Dotfiles are up-to-date.")
                elif local_changes and not is_behind:
                    typer.echo("⚠ You have local changes that are not backed up:")
                    for f in report["changed_files"]:
                        typer.echo(f"    - {f}")
                    
                    if is_ahead:
                        typer.echo(f"\n  (Local is {report.get('ahead_count', 0)} commit(s) ahead of remote)")
                    
                    typer.echo("\nTo backup these changes, run: freckle backup")
                elif not local_changes and is_behind:
                    behind_count = report.get('behind_count', 0)
                    typer.echo(f"↓ Remote repository ({branch_name}) has {behind_count} new commit(s).")
                    typer.echo("\nTo update your local files, run: freckle update")
                elif local_changes and is_behind:
                    typer.echo("‼ CONFLICT: You have local changes AND remote has new commits.")
                    typer.echo(f"  Local Commit : {report['local_commit']}")
                    typer.echo(f"  Remote Commit: {report['remote_commit']}")
                    typer.echo(f"  Behind by: {report.get('behind_count', 0)} commit(s)")
                    
                    typer.echo("\nLocal changes:")
                    for f in report["changed_files"]:
                        typer.echo(f"    - {f}")
                        
                    typer.echo("\nOptions to resolve conflict:")
                    typer.echo("  - To keep local changes and backup: freckle backup")
                    typer.echo("  - To discard local changes and update: freckle update --force")
                elif is_ahead and not local_changes:
                    ahead_count = report.get('ahead_count', 0)
                    typer.echo(f"↑ Local is {ahead_count} commit(s) ahead of remote.")
                    typer.echo("\nTo push, run: freckle backup")
                elif report.get("remote_branch_missing") and not local_changes:
                    typer.echo("↑ Local branch has no remote counterpart.")
                    typer.echo("\nTo push, run: freckle backup")

        for manager in tool_managers:
            if manager.bin_name in enabled_modules:
                manager.setup()
        
        typer.echo(f"\n--- {action_name} Complete! ---\n")
        
    except Exception as e:
        logger.error(f"Freckle failed: {e}")
        raise typer.Exit(1)


@app.command()
def backup(
    message: Optional[str] = typer.Option(None, "-m", "--message", help="Custom commit message"),
    no_push: bool = typer.Option(False, "--no-push", help="Commit locally but don't push"),
):
    """Commit and push local changes to remote.
    
    Commits any uncommitted changes in your dotfiles and pushes them
    to the remote repository.
    """
    setup_logging()
    config = _get_config()
    
    dotfiles = _get_dotfiles_manager(config)
    if not dotfiles:
        typer.echo("No dotfiles repository configured. Run 'freckle init' first.", err=True)
        raise typer.Exit(1)
    
    dotfiles_dir = Path(config.get("dotfiles.dir")).expanduser()
    if not dotfiles_dir.is_absolute():
        dotfiles_dir = env.home / dotfiles_dir
    
    if not dotfiles_dir.exists():
        typer.echo("Dotfiles repository not found. Run 'freckle sync' first.", err=True)
        raise typer.Exit(1)
    
    report = dotfiles.get_detailed_status()
    
    if not report["has_local_changes"] and not report.get("is_ahead", False):
        typer.echo("✓ Nothing to backup - already up-to-date.")
        return
    
    if report["has_local_changes"]:
        typer.echo("Backing up changed file(s):")
        for f in report["changed_files"]:
            typer.echo(f"  - {f}")
    
    if report.get("is_ahead", False):
        typer.echo(f"Pushing {report.get('ahead_count', 0)} unpushed commit(s)...")
    
    commit_msg = message or f"Backup from {env.os_info['pretty_name']}"
    
    if report["has_local_changes"]:
        if no_push:
            # Commit only - use git directly
            try:
                dotfiles._git("add", "-A")
                dotfiles._git("commit", "-m", commit_msg)
                result = {"success": True, "committed": True, "pushed": False}
            except Exception as e:
                result = {"success": False, "error": str(e)}
        else:
            result = dotfiles.commit_and_push(commit_msg)
    else:
        # Just push existing commits
        result = dotfiles.push() if not no_push else {"success": True}
    
    if result["success"]:
        if no_push:
            typer.echo("✓ Changes committed locally.")
        else:
            typer.echo("✓ Backed up successfully.")
    elif result.get("committed") and not result.get("pushed"):
        typer.echo(f"⚠ Committed locally but push failed: {result['error']}")
    else:
        typer.echo(f"✗ Backup failed: {result.get('error', 'Unknown error')}", err=True)
        raise typer.Exit(1)


@app.command()
def update(
    force: bool = typer.Option(False, "--force", "-f", help="Discard local changes and update"),
):
    """Pull and apply remote changes.
    
    Updates your local dotfiles to match the remote repository.
    If you have local changes, use --force to discard them.
    """
    setup_logging()
    config = _get_config()
    
    dotfiles = _get_dotfiles_manager(config)
    if not dotfiles:
        typer.echo("No dotfiles repository configured. Run 'freckle init' first.", err=True)
        raise typer.Exit(1)
    
    dotfiles_dir = Path(config.get("dotfiles.dir")).expanduser()
    if not dotfiles_dir.is_absolute():
        dotfiles_dir = env.home / dotfiles_dir
    
    if not dotfiles_dir.exists():
        typer.echo("Dotfiles repository not found. Run 'freckle sync' first.", err=True)
        raise typer.Exit(1)
    
    report = dotfiles.get_detailed_status()
    
    if report["has_local_changes"] and not force:
        typer.echo("⚠ You have local changes:")
        for f in report["changed_files"]:
            typer.echo(f"    - {f}")
        typer.echo("\nUse --force to discard these changes and update.")
        raise typer.Exit(1)
    
    if not report.get("is_behind", False):
        typer.echo("✓ Already up-to-date with remote.")
        return
    
    behind_count = report.get('behind_count', 0)
    typer.echo(f"Fetching {behind_count} new commit(s) from remote...")
    
    dotfiles.force_checkout()
    typer.echo("✓ Updated to latest remote version.")


@app.command()
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
    
    config = _get_config()
    
    dotfiles = _get_dotfiles_manager(config)
    if not dotfiles:
        typer.echo("Dotfiles not configured. Run 'freckle init' first.", err=True)
        raise typer.Exit(1)
    
    dotfiles_dir = Path(config.get("dotfiles.dir")).expanduser()
    if not dotfiles_dir.is_absolute():
        dotfiles_dir = env.home / dotfiles_dir
    
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


@app.command()
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
    
    config = _get_config()
    
    dotfiles = _get_dotfiles_manager(config)
    if not dotfiles:
        typer.echo("Dotfiles not configured. Run 'freckle init' first.", err=True)
        raise typer.Exit(1)
    
    dotfiles_dir = Path(config.get("dotfiles.dir")).expanduser()
    if not dotfiles_dir.is_absolute():
        dotfiles_dir = env.home / dotfiles_dir
    
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


@app.command()
def status():
    """Show current setup status and check for updates."""
    setup_logging()
    config = _get_config()
    
    repo_url = config.get("dotfiles.repo_url")
    dotfiles_dir = Path(config.get("dotfiles.dir")).expanduser()
    if not dotfiles_dir.is_absolute():
        dotfiles_dir = env.home / dotfiles_dir
    branch = config.get("dotfiles.branch")
    
    typer.echo(f"\n--- freckle Status ---")
    typer.echo(f"OS     : {env.os_info['pretty_name']} ({env.os_info['machine']})")
    typer.echo(f"Kernel : {env.os_info['release']}")
    typer.echo(f"User   : {env.user}")
    
    pkg_mgr = SystemPackageManager(env)
    
    dotfiles = None
    if repo_url:
        dotfiles = DotfilesManager(repo_url, dotfiles_dir, env.home, branch)

    tool_managers = _get_tool_managers(pkg_mgr)
    
    # Freckle config status
    config_path = env.home / ".freckle.yaml"
    typer.echo("\nConfiguration:")
    if config_path.exists():
        if dotfiles:
            file_status = dotfiles.get_file_sync_status(".freckle.yaml")
            status_str = {
                "up-to-date": "✓ up-to-date",
                "modified": "⚠ modified locally",
                "behind": "↓ update available (behind remote)",
                "untracked": "✗ not tracked in dotfiles",
                "missing": "✓ local only",
                "not-found": "✓ local only",
                "error": "⚠ error checking status"
            }.get(file_status, f"status: {file_status}")
            typer.echo(f"  .freckle.yaml : {status_str}")
        else:
            typer.echo(f"  .freckle.yaml : ✓ exists (dotfiles not configured)")
    else:
        typer.echo(f"  .freckle.yaml : ✗ not found (run 'freckle init')")

    # Collect all config files associated with tool managers
    tool_config_files = set()
    
    typer.echo("\nCore Tools:")
    for manager in tool_managers:
        info = pkg_mgr.get_binary_info(manager.bin_name)
        if info["found"]:
            typer.echo(f"  {manager.name}:")
            typer.echo(f"    Binary : {info['path']} ({info['version']})")
        else:
            typer.echo(f"  {manager.name}: ✗ not found in PATH")
            continue

        if dotfiles:
            for cfg in manager.config_files:
                tool_config_files.add(cfg)
                file_status = dotfiles.get_file_sync_status(cfg)
                if file_status == "not-found":
                    continue
                    
                status_str = {
                    "up-to-date": "✓ up-to-date",
                    "modified": "⚠ modified locally",
                    "behind": "↓ update available (behind remote)",
                    "untracked": "✗ not tracked",
                    "missing": "✗ missing from home",
                    "error": "⚠ error checking status"
                }.get(file_status, f"status: {file_status}")
                
                typer.echo(f"    Config : {status_str} ({cfg})")
    
    # Show all other tracked files
    if dotfiles:
        all_tracked = dotfiles.get_tracked_files()
        other_tracked = [
            f for f in all_tracked 
            if f != ".freckle.yaml" and f not in tool_config_files
        ]
        
        if other_tracked:
            typer.echo("\nOther Tracked Files:")
            for f in sorted(other_tracked):
                file_status = dotfiles.get_file_sync_status(f)
                status_str = {
                    "up-to-date": "✓",
                    "modified": "⚠ modified",
                    "behind": "↓ behind",
                    "missing": "✗ missing",
                    "error": "?"
                }.get(file_status, "?")
                typer.echo(f"  {status_str} {f}")
            
    # Global Dotfiles Status
    if not repo_url:
        typer.echo("\nDotfiles: Not configured (run 'freckle init')")
    else:
        typer.echo(f"\nDotfiles ({repo_url}):")
        try:
            report = dotfiles.get_detailed_status()
            if not report["initialized"]:
                typer.echo("  Status: Not initialized")
            else:
                branch_info = report.get('branch_info', {})
                effective_branch = report.get('branch', branch)
                
                reason = branch_info.get('reason', 'exact')
                if reason == 'exact':
                    typer.echo(f"  Branch: {effective_branch}")
                elif reason == 'main_master_swap':
                    typer.echo(f"  Branch: {effective_branch}")
                    typer.echo(f"    Note: '{branch_info.get('configured')}' not found, using '{effective_branch}'")
                elif reason == 'not_found':
                    typer.echo(f"  Branch: {effective_branch} (configured, but not found!)")
                    available = branch_info.get('available', [])
                    if available:
                        typer.echo(f"    Available branches: {', '.join(available)}")
                    else:
                        typer.echo(f"    No branches found - is this repo initialized?")
                else:
                    typer.echo(f"  Branch: {effective_branch}")
                    if branch_info.get('message'):
                        typer.echo(f"    Note: {branch_info['message']}")
                
                typer.echo(f"  Local Commit : {report['local_commit']}")
                
                if report.get("remote_branch_missing"):
                    typer.echo(f"  Remote Commit: ✗ No origin/{effective_branch} branch!")
                    typer.echo(f"    The local '{effective_branch}' branch has no remote counterpart.")
                    typer.echo(f"    To push it: freckle backup")
                else:
                    typer.echo(f"  Remote Commit: {report.get('remote_commit', 'N/A')}")
                
                if report.get("fetch_failed"):
                    typer.echo("  Remote Status: ⚠ Could not fetch (offline?)")
                
                if report["has_local_changes"]:
                    typer.echo("  Local Changes: Yes (uncommitted changes)")
                else:
                    typer.echo("  Local Changes: No")
                
                if report.get("remote_branch_missing"):
                    pass
                elif report.get("is_ahead"):
                    typer.echo(f"  Ahead: Yes ({report.get('ahead_count', 0)} commits not pushed)")
                    
                if report.get("is_behind"):
                    typer.echo(f"  Behind: Yes ({report.get('behind_count', 0)} commits to pull)")
                elif not report.get("fetch_failed") and not report.get("remote_branch_missing"):
                    typer.echo("  Behind: No (up to date)")
                    
        except Exception as e:
            typer.echo(f"  Error checking status: {e}")
    typer.echo("")


@app.command()
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
    config = _get_config()
    
    dotfiles = _get_dotfiles_manager(config)
    if not dotfiles:
        typer.echo("Dotfiles not configured. Run 'freckle init' first.", err=True)
        raise typer.Exit(1)
    
    dotfiles_dir = Path(config.get("dotfiles.dir")).expanduser()
    if not dotfiles_dir.is_absolute():
        dotfiles_dir = env.home / dotfiles_dir
    
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


@app.command()
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
    config = _get_config()
    
    dotfiles = _get_dotfiles_manager(config)
    if not dotfiles:
        typer.echo("Dotfiles not configured. Run 'freckle init' first.", err=True)
        raise typer.Exit(1)
    
    dotfiles_dir = Path(config.get("dotfiles.dir")).expanduser()
    if not dotfiles_dir.is_absolute():
        dotfiles_dir = env.home / dotfiles_dir
    
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


@app.command()
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
    config = _get_config()
    
    dotfiles = _get_dotfiles_manager(config)
    if not dotfiles:
        typer.echo("Dotfiles not configured. Run 'freckle init' first.", err=True)
        raise typer.Exit(1)
    
    dotfiles_dir = Path(config.get("dotfiles.dir")).expanduser()
    if not dotfiles_dir.is_absolute():
        dotfiles_dir = env.home / dotfiles_dir
    
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


@app.command()
def version():
    """Show the version of freckle."""
    typer.echo(f"freckle version {get_version()}")


def main():
    """Main entry point for the freckle CLI."""
    setup_logging()
    app()
