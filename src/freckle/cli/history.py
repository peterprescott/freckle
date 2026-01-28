"""History and diff commands for freckle CLI - view git history of dotfiles."""

import subprocess
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import typer

from ..dotfiles import GitHistoryService
from .helpers import (
    env,
    get_config,
    get_dotfiles_dir,
    normalize_to_home_relative,
)
from .output import console, diff_add, diff_remove, error, info, muted, plain


def get_history_service(dotfiles_dir: Path) -> GitHistoryService:
    """Create a GitHistoryService for the dotfiles repo."""
    return GitHistoryService(dotfiles_dir, env.home)


def register(app: typer.Typer) -> None:
    """Register history and diff commands with the app."""
    app.command()(history)
    app.command()(diff)


def history(
    tool_or_path: Optional[str] = typer.Argument(
        None,
        help="Tool name or file path. Omit to show all commits.",
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
    oneline: bool = typer.Option(
        False,
        "--oneline",
        help="Compact one-line format (for general history)",
    ),
):
    """Show git commit history for your dotfiles.

    Without arguments, shows the general commit history of your dotfiles repo.
    With a tool/path argument, shows history for that specific file.

    Examples:
        freckle history                   # All recent commits
        freckle history --oneline         # Compact format
        freckle history nvim              # History for nvim config
        freckle history ~/.zshrc          # History for zshrc
        freckle history tmux -n 5         # Last 5 commits for tmux
        freckle history nvim --files      # Show files changed per commit
    """
    config = get_config()
    dotfiles_dir = get_dotfiles_dir(config)

    if not dotfiles_dir.exists():
        error("Dotfiles directory not found.")
        muted("Run 'freckle init' first to set up your dotfiles.")
        raise typer.Exit(1)

    # If no tool specified, show general commit history
    if tool_or_path is None:
        show_general_history(dotfiles_dir, limit, oneline)
        return

    # Resolve tool_or_path to actual file paths
    file_paths = resolve_to_repo_paths(tool_or_path, config, dotfiles_dir)

    if not file_paths:
        error(f"Could not find config files for: {tool_or_path}")
        muted("\nTry using a file path directly, e.g.:")
        muted("  freckle history ~/.config/nvim/init.lua")
        raise typer.Exit(1)

    # Get history for these files
    commits = get_file_history(dotfiles_dir, file_paths, limit)

    if not commits:
        plain(f"No history found for: {tool_or_path}")
        muted("\nThis file may not be tracked in your dotfiles repo.")
        return

    # Display header
    if len(file_paths) == 1:
        plain(f"History for {file_paths[0]}:\n")
    else:
        plain(f"History for {tool_or_path} ({len(file_paths)} files):\n")

    # Display commits with diff preview
    for commit in commits:
        display_commit(commit, show_files, dotfiles_dir, file_paths)

    if len(commits) == limit:
        muted(f"\n[Showing {limit} commits. Use --limit to see more]")


def show_general_history(
    dotfiles_dir: Path, limit: int, oneline: bool
) -> None:
    """Show general commit history for the dotfiles repo."""
    try:
        if oneline:
            format_str = "%h %s"
        else:
            format_str = "%h|%aI|%an|%s"

        cmd = [
            "git",
            "--git-dir",
            str(dotfiles_dir),
            "log",
            f"--format={format_str}",
            f"-n{limit}",
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            plain("No commits yet.")
            return

        if not result.stdout.strip():
            plain("No commits yet.")
            return

        plain(f"Recent commits (last {limit}):\n")

        if oneline:
            # Simple oneline format
            for line in result.stdout.strip().split("\n"):
                if line:
                    parts = line.split(" ", 1)
                    if len(parts) == 2:
                        console.print(
                            f"[yellow]{parts[0]}[/yellow] {parts[1]}"
                        )
                    else:
                        plain(line)
        else:
            # Detailed format with relative dates
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue

                parts = line.split("|", 3)
                if len(parts) < 4:
                    continue

                commit_hash, date_str, author, subject = parts

                # Parse date
                try:
                    date = datetime.fromisoformat(
                        date_str.replace("Z", "+00:00")
                    )
                    date_display = format_relative_date(date)
                except ValueError:
                    date_display = date_str[:10]

                console.print(
                    f"[bold yellow]{commit_hash}[/bold yellow] - "
                    f"[green]{date_display}[/green] - "
                    f"{subject}"
                )

    except subprocess.TimeoutExpired:
        error("Timeout fetching history.")
    except Exception as e:
        error(f"Error: {e}")


def diff(
    commit1: str = typer.Argument(
        ...,
        help="First commit hash (older)",
    ),
    commit2: str = typer.Argument(
        ...,
        help="Second commit hash (newer)",
    ),
    tool_or_path: str = typer.Argument(
        ...,
        help="Tool name (e.g., 'nvim') or file path",
    ),
    context: int = typer.Option(
        3,
        "--context",
        "-C",
        help="Number of context lines to show",
    ),
):
    """Compare a dotfile between two commits.

    Shows the full diff between two versions of a dotfile.

    Examples:
        freckle diff abc123 def456 nvim       # Compare nvim config
        freckle diff abc123 HEAD ~/.zshrc     # Compare zshrc to current
        freckle diff abc123 def456 tmux -C 5  # Show 5 lines of context
    """
    config = get_config()
    dotfiles_dir = get_dotfiles_dir(config)

    if not dotfiles_dir.exists():
        error("Dotfiles directory not found.")
        raise typer.Exit(1)

    # Use the history service for git operations
    history_svc = get_history_service(dotfiles_dir)

    # Validate commits exist
    if not history_svc.is_valid_commit(commit1):
        error(f"Invalid commit: {commit1}")
        raise typer.Exit(1)

    if not history_svc.is_valid_commit(commit2):
        error(f"Invalid commit: {commit2}")
        raise typer.Exit(1)

    # Resolve tool to file paths
    file_paths = resolve_to_repo_paths(tool_or_path, config, dotfiles_dir)

    if not file_paths:
        error(f"Could not find config files for: {tool_or_path}")
        raise typer.Exit(1)

    # Get commit info for display
    info1 = history_svc.get_commit_subject(commit1)
    info2 = history_svc.get_commit_subject(commit2)

    plain(f"Comparing {tool_or_path}:")
    console.print(f"  [red]{commit1[:7]}[/red] {info1 or ''}")
    console.print(f"  [green]{commit2[:7]}[/green] {info2 or ''}")
    plain("")

    # Show diff for each file
    for file_path in file_paths:
        diff_output = get_diff_between_commits(
            dotfiles_dir, commit1, commit2, file_path, context
        )

        if diff_output:
            console.print(f"[bold]─── {file_path} ───[/bold]")
            display_colored_diff(diff_output)
            plain("")
        else:
            console.print(f"[bold]─── {file_path} ───[/bold]")
            muted("  (no changes)")
            plain("")


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
    # Special case: "freckle" refers to the freckle config itself
    if tool_or_path == "freckle":
        # Return whichever config file exists
        for filename in (".freckle.yaml", ".freckle.yml"):
            if (env.home / filename).exists():
                return [filename]
        return [".freckle.yaml"]  # Default if neither exists

    # Direct file path (~ or absolute or relative with .)
    if (
        tool_or_path.startswith("~")
        or tool_or_path.startswith("/")
        or tool_or_path.startswith(".")
    ):
        relative = normalize_to_home_relative(tool_or_path, home=env.home)
        if relative is not None:
            return [relative]
        # Outside home - return as-is (unusual case)
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
            files_changed = get_commit_files(
                dotfiles_dir, commit_hash, file_paths
            )

            # Parse date
            try:
                date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                date_display = format_relative_date(date)
            except ValueError:
                date_display = date_str[:10]

            commits.append(
                {
                    "hash": commit_hash,
                    "date": date_display,
                    "date_raw": date_str,
                    "author": author,
                    "subject": subject,
                    "files": files_changed,
                }
            )

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

        files = [
            f.strip() for f in result.stdout.strip().split("\n") if f.strip()
        ]

        # Filter if requested
        if filter_paths:
            # Include file if it matches any filter path (file or directory)
            filtered = []
            for f in files:
                for filter_path in filter_paths:
                    if f == filter_path or f.startswith(
                        filter_path.rstrip("/") + "/"
                    ):
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


def display_commit(
    commit: dict,
    show_files: bool = False,
    dotfiles_dir: Optional[Path] = None,
    file_paths: Optional[List[str]] = None,
) -> None:
    """Display a single commit entry with diff preview."""
    console.print(
        f"[bold yellow]{commit['hash']}[/bold yellow] - "
        f"[green]{commit['date']}[/green] - "
        f"{commit['author']}"
    )
    plain(f"    {commit['subject']}")

    if show_files and commit["files"]:
        muted(f"    {len(commit['files'])} file(s) changed:")
        for f in commit["files"][:5]:
            muted(f"      {f}")
        if len(commit["files"]) > 5:
            muted(f"      ... and {len(commit['files']) - 5} more")

    # Show diff preview if we have the dotfiles_dir
    if dotfiles_dir and file_paths:
        diff_lines = get_commit_diff_preview(
            dotfiles_dir, commit["hash"], file_paths, max_lines=4
        )
        if diff_lines:
            for line in diff_lines:
                if line.startswith("+"):
                    diff_add(f"    {line}")
                elif line.startswith("-"):
                    diff_remove(f"    {line}")
                else:
                    muted(f"    {line}")

    plain("")  # Blank line between commits


def is_valid_commit(dotfiles_dir: Path, commit: str) -> bool:
    """Check if a commit reference is valid."""
    try:
        result = subprocess.run(
            [
                "git",
                "--git-dir",
                str(dotfiles_dir),
                "rev-parse",
                "--verify",
                f"{commit}^{{commit}}",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


def get_commit_info(dotfiles_dir: Path, commit: str) -> Optional[str]:
    """Get commit subject line."""
    try:
        result = subprocess.run(
            [
                "git",
                "--git-dir",
                str(dotfiles_dir),
                "log",
                "-1",
                "--format=%s",
                commit,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def get_commit_diff_preview(
    dotfiles_dir: Path,
    commit_hash: str,
    file_paths: List[str],
    max_lines: int = 4,
) -> List[str]:
    """Get a short preview of the diff for a commit.

    Returns a few lines showing additions/deletions.
    """
    try:
        cmd = [
            "git",
            "--git-dir",
            str(dotfiles_dir),
            "diff-tree",
            "-p",
            "--no-commit-id",
            "-U0",  # No context lines for compact preview
            commit_hash,
            "--",
        ] + file_paths

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            return []

        # Parse diff output, extract meaningful lines
        lines = []
        for line in result.stdout.split("\n"):
            # Skip headers and metadata
            if line.startswith("diff --git"):
                continue
            if line.startswith("index "):
                continue
            if line.startswith("---") or line.startswith("+++"):
                continue
            if line.startswith("@@"):
                continue
            if not line.strip():
                continue

            # Include +/- lines
            if line.startswith("+") or line.startswith("-"):
                # Truncate long lines
                display_line = line[:60] + "..." if len(line) > 60 else line
                lines.append(display_line)

                if len(lines) >= max_lines:
                    break

        return lines

    except Exception:
        return []


def get_diff_between_commits(
    dotfiles_dir: Path,
    commit1: str,
    commit2: str,
    file_path: str,
    context: int = 3,
) -> Optional[str]:
    """Get the diff between two commits for a specific file."""
    try:
        cmd = [
            "git",
            "--git-dir",
            str(dotfiles_dir),
            "diff",
            f"-U{context}",
            commit1,
            commit2,
            "--",
            file_path,
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0 and result.stdout.strip():
            return result.stdout
        return None

    except Exception:
        return None


def display_colored_diff(diff_output: str) -> None:
    """Display a colorized diff output."""
    for line in diff_output.split("\n"):
        if line.startswith("+") and not line.startswith("+++"):
            diff_add(line)
        elif line.startswith("-") and not line.startswith("---"):
            diff_remove(line)
        elif line.startswith("@@"):
            info(line)
        elif line.startswith("diff --git"):
            continue  # Skip, we show our own header
        elif line.startswith("index "):
            continue  # Skip index line
        else:
            plain(line)
