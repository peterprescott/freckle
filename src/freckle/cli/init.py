"""Init command for freckle CLI."""

import shutil
import subprocess
from pathlib import Path

import typer
import yaml

from ..dotfiles import DotfilesManager
from ..utils import validate_git_url, verify_git_url_accessible
from .helpers import CONFIG_PATH, env, logger
from .output import error, muted, plain, success, warning


def register(app: typer.Typer) -> None:
    """Register the init command with the app."""
    app.command()(init)


def _try_clone_from_existing_config() -> bool:
    """Check if config exists but dotfiles aren't cloned, and clone if so.

    Returns:
        True if we handled the situation (cloned or already set up)
        False if config is incomplete or we should proceed with normal init
    """
    try:
        with open(CONFIG_PATH) as f:
            config = yaml.safe_load(f)
    except Exception:
        return False

    if not config or "dotfiles" not in config:
        return False

    dotfiles_config = config.get("dotfiles", {})
    repo_url = dotfiles_config.get("repo_url", "")
    dotfiles_dir = dotfiles_config.get("dir", ".dotfiles")
    branch = dotfiles_config.get("branch", "main")

    if not repo_url:
        return False

    # Resolve dotfiles path
    dotfiles_path = Path(dotfiles_dir).expanduser()
    if not dotfiles_path.is_absolute():
        dotfiles_path = env.home / dotfiles_path

    # Check if dotfiles are already set up
    if dotfiles_path.exists() and (dotfiles_path / "HEAD").exists():
        # Already cloned - show helpful message
        plain("Dotfiles already configured and cloned.")
        muted(f"  Config: {CONFIG_PATH}")
        muted(f"  Repo: {dotfiles_path}")
        plain("\nRun 'freckle status' to see current state.")
        return True

    # Config exists but dotfiles not cloned - clone them
    plain("--- freckle Initialization ---\n")
    plain(f"Found existing config at {CONFIG_PATH}")
    plain(f"Dotfiles not yet cloned. Cloning from: {repo_url}\n")

    dotfiles = DotfilesManager(repo_url, dotfiles_path, env.home, branch)
    try:
        dotfiles.setup()
        success("Dotfiles cloned and set up!")
        plain("\nYour dotfiles are now ready.")
        muted("Run 'freckle status' to see current state.")
        return True
    except Exception as e:
        logger.error(f"Failed to clone: {e}")
        error(f"Could not clone repository: {e}")
        muted("  Check your repo URL and network connection.")
        muted("  You can try again with: freckle init")
        raise typer.Exit(1)


def init(
    force: bool = typer.Option(
        False, "--force", "-f", help="Overwrite existing configuration"
    ),
):
    """Initialize configuration and set up dotfiles repository.

    Offers two modes:
    1. Clone an existing dotfiles repository
    2. Create a new dotfiles repository from scratch

    If config already exists but dotfiles aren't cloned, clones them.
    """
    if CONFIG_PATH.exists() and not force:
        # Config exists - check if we just need to clone dotfiles
        if _try_clone_from_existing_config():
            return
        error(f"Config exists at {CONFIG_PATH}. Use --force to overwrite.")
        raise typer.Exit(1)

    plain("--- freckle Initialization ---\n")

    # Ask if they have an existing repo
    choice = (
        typer.prompt(
            "Do you have an existing dotfiles repository? [y/N]", default="n"
        )
        .strip()
        .lower()
    )

    if choice in ["y", "yes"]:
        _init_clone_existing()
    else:
        _init_create_new()


def _init_clone_existing() -> None:
    """Initialize by cloning an existing dotfiles repo."""
    plain("\n--- Clone Existing Repository ---\n")

    # Get and validate repository URL
    while True:
        repo_url = typer.prompt("Enter your dotfiles repository URL").strip()

        if not repo_url:
            plain("  Repository URL is required.")
            continue

        if not validate_git_url(repo_url):
            plain("  Invalid URL format. Please enter a valid git URL.")
            muted("  Examples: https://github.com/user/repo.git")
            muted("            git@github.com:user/repo.git")
            continue

        # Try to verify the URL is accessible
        plain("  Verifying repository access...")
        accessible, err = verify_git_url_accessible(repo_url)
        if not accessible:
            warning(f"Could not access repository: {err}", prefix="  ⚠")
            confirm = (
                typer.prompt("  Continue anyway? [y/N]", default="n")
                .strip()
                .lower()
            )
            if confirm not in ["y", "yes"]:
                continue
        else:
            success("Repository accessible", prefix="  ✓")

        break

    branch = (
        typer.prompt("Enter your preferred branch", default="main")
        .strip()
        .lower()
    )
    dotfiles_dir = typer.prompt(
        "Enter directory for bare repo", default=".dotfiles"
    ).strip()

    config_data = {
        "dotfiles": {
            "repo_url": repo_url,
            "branch": branch,
            "dir": dotfiles_dir,
        },
        "modules": ["dotfiles", "zsh", "tmux", "nvim"],
    }

    with open(CONFIG_PATH, "w") as f:
        yaml.dump(config_data, f, default_flow_style=False)

    logger.info(f"Created configuration at {CONFIG_PATH}")

    # Clone the repository now
    plain("\nCloning your dotfiles...")
    dotfiles_path = Path(dotfiles_dir).expanduser()
    if not dotfiles_path.is_absolute():
        dotfiles_path = env.home / dotfiles_path

    dotfiles = DotfilesManager(repo_url, dotfiles_path, env.home, branch)
    try:
        dotfiles.setup()
        success("Dotfiles cloned and set up!")
        plain("\nYour dotfiles are now ready. Next steps:")
        muted("  - Edit your config files as needed")
        muted("  - Run 'freckle save' to save changes to the cloud")
    except Exception as e:
        logger.error(f"Failed to clone: {e}")
        warning(f"Could not clone repository: {e}")
        muted("  You can try again later with: freckle fetch")


def _init_create_new() -> None:
    """Initialize by creating a new dotfiles repo."""
    plain("\n--- Create New Dotfiles Repository ---\n")

    repo_url = ""

    # Check if gh CLI is available
    has_gh = shutil.which("gh") is not None

    if has_gh:
        plain("GitHub CLI detected. Create a new repo on GitHub?")
        create_gh = (
            typer.prompt(
                "Create repo with 'gh repo create'? [Y/n]", default="y"
            )
            .strip()
            .lower()
        )

        if create_gh not in ["n", "no"]:
            repo_name = typer.prompt(
                "Repository name", default="dotfiles"
            ).strip()
            private = (
                typer.prompt("Make it private? [Y/n]", default="y")
                .strip()
                .lower()
            )
            visibility = (
                "--private" if private not in ["n", "no"] else "--public"
            )

            plain(f"\n  Creating {repo_name} on GitHub...")
            try:
                result = subprocess.run(
                    [
                        "gh",
                        "repo",
                        "create",
                        repo_name,
                        visibility,
                        "--confirm",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if result.returncode == 0:
                    repo_url = result.stdout.strip()
                    if not repo_url:
                        user_result = subprocess.run(
                            ["gh", "api", "user", "-q", ".login"],
                            capture_output=True,
                            text=True,
                        )
                        if user_result.returncode == 0:
                            username = user_result.stdout.strip()
                            repo_url = (
                                f"https://github.com/{username}/{repo_name}.git"
                            )
                    success(f"Created: {repo_url}", prefix="  ✓")
                else:
                    error(f"Failed: {result.stderr.strip()}", prefix="  ✗")
                    muted("  Continuing without remote.")
            except Exception as e:
                error(f"Error: {e}", prefix="  ✗")
                muted("  Continuing without remote.")

    # If we don't have a URL yet, ask for one
    if not repo_url:
        if not has_gh:
            plain("To sync across machines, you'll need a remote repository.")
            plain("Create one on GitHub/GitLab, then enter the URL here.")
            muted("Or leave blank to set up locally only.\n")
        else:
            plain("\nEnter repository URL, or blank to skip:\n")

        while True:
            url_input = typer.prompt(
                "Repository URL (or blank)", default=""
            ).strip()

            if not url_input:
                break

            if not validate_git_url(url_input):
                warning("URL format looks unusual.")

            plain("  Checking repository access...")
            accessible, err = verify_git_url_accessible(url_input)
            if not accessible:
                error(f"Cannot access repository: {err}", prefix="  ✗")
                retry = (
                    typer.prompt("  Try a different URL? [Y/n]", default="y")
                    .strip()
                    .lower()
                )
                if retry in ["n", "no"]:
                    break
                continue
            else:
                success("Repository accessible", prefix="  ✓")
                repo_url = url_input
                break

    branch = typer.prompt("Enter branch name", default="main").strip().lower()
    dotfiles_dir = typer.prompt(
        "Enter directory for bare repo", default=".dotfiles"
    ).strip()

    # Ask which files to track initially
    plain(
        "\nWhich dotfiles do you want to track? (Enter comma-separated list)"
    )
    muted("Examples: .zshrc, .bashrc, .gitconfig, .tmux.conf, .config/nvim")
    muted(
        "Or press Enter for common defaults: "
        ".freckle.yaml, .zshrc, .gitconfig, .tmux.conf\n"
    )

    files_input = typer.prompt("Files to track", default="").strip()
    if files_input:
        initial_files = [
            f.strip() for f in files_input.split(",") if f.strip()
        ]
        if ".freckle.yaml" not in initial_files:
            initial_files.insert(0, ".freckle.yaml")
    else:
        initial_files = [".freckle.yaml", ".zshrc", ".gitconfig", ".tmux.conf"]

    # Check if dotfiles directory already exists
    dotfiles_path = Path(dotfiles_dir).expanduser()
    if not dotfiles_path.is_absolute():
        dotfiles_path = env.home / dotfiles_path
    if dotfiles_path.exists():
        warning(f"Directory already exists: {dotfiles_path}")
        choice = (
            typer.prompt("Remove it and start fresh? [y/N]", default="n")
            .strip()
            .lower()
        )
        if choice in ["y", "yes"]:
            shutil.rmtree(dotfiles_path)
            muted(f"  Removed {dotfiles_path}")
        else:
            muted(
                "  Aborting. Remove the directory manually "
                "or choose a different location."
            )
            raise typer.Exit(1)

    # Save config FIRST so it can be included in the initial commit
    config_data = {
        "dotfiles": {
            "repo_url": repo_url or f"file://{dotfiles_path}",
            "branch": branch,
            "dir": dotfiles_dir,
        },
        "modules": ["dotfiles", "zsh", "tmux", "nvim"],
    }

    with open(CONFIG_PATH, "w") as f:
        yaml.dump(config_data, f, default_flow_style=False)

    logger.info(f"Created configuration at {CONFIG_PATH}")

    # Check which files exist
    all_files_to_track = []
    for f in initial_files:
        path = env.home / f
        if path.exists():
            all_files_to_track.append(f)
        else:
            muted(f"  Note: {f} doesn't exist yet, skipping")

    if not all_files_to_track:
        plain("\nNo existing files to track. You can add files later with:")
        muted("  freckle track <file>")

    # Create the repo
    dotfiles = DotfilesManager(repo_url or "", dotfiles_path, env.home, branch)

    try:
        dotfiles.create_new(
            initial_files=all_files_to_track, remote_url=repo_url or None
        )
        success(f"Created new dotfiles repository at {dotfiles_dir}")

        if all_files_to_track:
            files_list = ", ".join(all_files_to_track)
            n = len(all_files_to_track)
            success(f"Tracking {n} file(s): {files_list}")
    except Exception as e:
        logger.error(f"Failed to create repository: {e}")
        CONFIG_PATH.unlink(missing_ok=True)
        raise typer.Exit(1)

    if repo_url:
        plain("\nNext steps:")
        muted("  1. Run 'freckle save' to save dotfiles to the cloud")
        muted("  2. On other machines, run 'freckle init' and choose option 1")
    else:
        plain("\nNext steps:")
        muted("  1. Create a repo on GitHub/GitLab")
        muted(
            f"  2. Add remote: git --git-dir={dotfiles_dir} "
            "remote add origin <url>"
        )
        muted(f"  3. Push: git --git-dir={dotfiles_dir} push -u origin main")
