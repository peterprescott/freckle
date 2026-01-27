"""History command for freckle CLI - view git history of dotfiles."""

import subprocess
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import typer

from .helpers import env, get_config, get_dotfiles_dir


def register(app: typer.Typer) -> None:
    """Register history command with the app."""
    app.command()(history)


def history(
    tool_or_path: str = typer.Argument(
        ...,
        help="Tool name (e.g., 'nvim') or file path (e.g., '~/.zshrc')",
    ),
    limit: int = typer.Option(
        20,
        "--limit",
        "-n",
        help="Number of commits to show",
    ),
    show_files: bool = typer.Option(
        False,
        "--files",
        "-f",
        help="Show files changed in each commit",
    ),
):
    """Show git commit history for a dotfile.

    View the history of changes to a specific dotfile or tool configuration.

    Examples:
        freckle history nvim                  # History for nvim config
        freckle history ~/.zshrc              # History for zshrc
        freckle history tmux --limit 5        # Last 5 commits for tmux
        freckle history nvim --files          # Show changed files in each commit
    """
    config = get_config()
    dotfiles_dir = get_dotfiles_dir(config)

    if not dotfiles_dir.exists():
        typer.echo("Dotfiles directory not found.", err=True)
        typer.echo("Run 'freckle init' first to set up your dotfiles.")
        raise typer.Exit(1)

    # Resolve tool_or_path to actual file paths
    file_paths = resolve_to_repo_paths(tool_or_path, config, dotfiles_dir)

    if not file_paths:
        typer.echo(f"Could not find config files for: {tool_or_path}", err=True)
        typer.echo("\nTry using a file path directly, e.g.:")
        typer.echo("  freckle history ~/.config/nvim/init.lua")
        raise typer.Exit(1)

    # Get history for these files
    commits = get_file_history(dotfiles_dir, file_paths, limit)

    if not commits:
        typer.echo(f"No history found for: {tool_or_path}")
        typer.echo("\nThis file may not be tracked in your dotfiles repo.")
        return

    # Display header
    if len(file_paths) == 1:
        typer.echo(f"History for {file_paths[0]}:\n")
    else:
        typer.echo(f"History for {tool_or_path} ({len(file_paths)} files):\n")

    # Display commits
    for commit in commits:
        display_commit(commit, show_files)

    if len(commits) == limit:
        typer.echo(f"\n[Showing {limit} commits. Use --limit to see more]")


def resolve_to_repo_paths(
    tool_or_path: str,
    config,
    dotfiles_dir: Path,
) -> List[str]:
    """Resolve a tool name or file path to repo-relative paths.

    Args:
        tool_or_path: Tool name (e.g., 'nvim') or file path
        config: Config object
        dotfiles_dir: Path to dotfiles repository

    Returns:
        List of repo-relative file paths, or empty list if not found
    """
    # Direct file path (~ or absolute)
    if tool_or_path.startswith("~") or tool_or_path.startswith("/"):
        expanded = Path(tool_or_path).expanduser()
        if expanded.is_absolute():
            try:
                relative = expanded.relative_to(env.home)
                return [str(relative)]
            except ValueError:
                return [str(expanded)]
        return [tool_or_path]

    # Relative path starting with dot (like .zshrc)
    if tool_or_path.startswith("."):
        return [tool_or_path]

    # Look up tool in freckle config - returns all config files for the tool
    tools_config = config.data.get("tools", {})
    if tool_or_path in tools_config:
        tool_data = tools_config[tool_or_path]
        config_files = tool_data.get("config", [])
        return config_files  # May be empty list if tool has no config defined

    # Tool not found in config
    return []


def get_file_history(
    dotfiles_dir: Path,
    file_paths: List[str],
    limit: int,
) -> List[dict]:
    """Get git log history for specific files.

    Args:
        dotfiles_dir: Path to bare git repo
        file_paths: List of repo-relative file paths
        limit: Maximum number of commits to return

    Returns:
        List of commit dicts with hash, date, author, message, files
    """
    try:
        # Build git log command
        # Format: hash|date|author|subject
        format_str = "%h|%aI|%an|%s"

        cmd = [
            "git",
            "--git-dir",
            str(dotfiles_dir),
            "log",
            f"--format={format_str}",
            f"-n{limit}",
            "--follow",  # Follow file renames
            "--",
        ] + file_paths

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            return []

        commits = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue

            parts = line.split("|", 3)
            if len(parts) < 4:
                continue

            commit_hash, date_str, author, subject = parts

            # Get files changed in this commit
            files_changed = get_commit_files(dotfiles_dir, commit_hash, file_paths)

            # Parse date
            try:
                date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                date_display = format_relative_date(date)
            except ValueError:
                date_display = date_str[:10]

            commits.append({
                "hash": commit_hash,
                "date": date_display,
                "date_raw": date_str,
                "author": author,
                "subject": subject,
                "files": files_changed,
            })

        return commits

    except subprocess.TimeoutExpired:
        return []
    except Exception:
        return []


def get_commit_files(
    dotfiles_dir: Path,
    commit_hash: str,
    filter_paths: Optional[List[str]] = None,
) -> List[str]:
    """Get list of files changed in a commit.

    Args:
        dotfiles_dir: Path to bare git repo
        commit_hash: Short or full commit hash
        filter_paths: Optional list of paths to filter by

    Returns:
        List of changed file paths
    """
    try:
        cmd = [
            "git",
            "--git-dir",
            str(dotfiles_dir),
            "diff-tree",
            "--no-commit-id",
            "--name-only",
            "-r",
            commit_hash,
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            return []

        files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]

        # Filter if requested
        if filter_paths:
            # Include file if it matches any filter path (file or directory)
            filtered = []
            for f in files:
                for filter_path in filter_paths:
                    if f == filter_path or f.startswith(filter_path.rstrip("/") + "/"):
                        filtered.append(f)
                        break
            return filtered

        return files

    except Exception:
        return []


def format_relative_date(date: datetime) -> str:
    """Format a date as a human-readable relative string."""
    now = datetime.now(date.tzinfo)
    diff = now - date

    if diff.days == 0:
        hours = diff.seconds // 3600
        if hours == 0:
            minutes = diff.seconds // 60
            if minutes == 0:
                return "just now"
            return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    elif diff.days == 1:
        return "yesterday"
    elif diff.days < 7:
        return f"{diff.days} days ago"
    elif diff.days < 30:
        weeks = diff.days // 7
        return f"{weeks} week{'s' if weeks != 1 else ''} ago"
    elif diff.days < 365:
        months = diff.days // 30
        return f"{months} month{'s' if months != 1 else ''} ago"
    else:
        return date.strftime("%Y-%m-%d")


def display_commit(commit: dict, show_files: bool = False) -> None:
    """Display a single commit entry."""
    typer.echo(
        typer.style(commit["hash"], fg=typer.colors.YELLOW, bold=True)
        + " - "
        + typer.style(commit["date"], fg=typer.colors.GREEN)
        + " - "
        + commit["author"]
    )
    typer.echo(f"    {commit['subject']}")

    if show_files and commit["files"]:
        typer.echo(
            typer.style(f"    {len(commit['files'])} file(s) changed:", dim=True)
        )
        for f in commit["files"][:5]:  # Limit to 5 files
            typer.echo(typer.style(f"      {f}", dim=True))
        if len(commit["files"]) > 5:
            typer.echo(typer.style(f"      ... and {len(commit['files']) - 5} more", dim=True))

    typer.echo("")  # Blank line between commits
