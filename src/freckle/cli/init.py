"""Init command for freckle CLI."""

import shutil
import subprocess
from pathlib import Path

import typer
import yaml

from ..dotfiles import DotfilesManager
from ..utils import setup_logging, validate_git_url, verify_git_url_accessible
from .helpers import env, logger


def register(app: typer.Typer) -> None:
    """Register the init command with the app."""
    app.command()(init)


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
