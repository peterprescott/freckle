"""Utility functions for the freckle package."""

import importlib.metadata
import logging
import re
import subprocess
import sys
from typing import Tuple


def setup_logging(verbose: bool = False):
    """Configure logging for freckle.

    Args:
        verbose: If True, set level to DEBUG. Otherwise WARNING.
    """
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def get_version() -> str:
    """Get the package version.

    Returns:
        Version string, or "(development)" if not installed as a package.
    """
    try:
        return importlib.metadata.version("freckle")
    except importlib.metadata.PackageNotFoundError:
        return "(development)"


def validate_git_url(url: str) -> bool:
    """Validate that a URL looks like a valid git repository URL.

    Accepts:
    - https://github.com/user/repo.git
    - git@github.com:user/repo.git
    - ssh://git@github.com/user/repo.git
    - /path/to/local/repo (local paths)
    - file:///path/to/repo

    Args:
        url: The URL to validate.

    Returns:
        True if the URL appears to be a valid git URL.
    """
    if not url:
        return False

    # Local path
    if url.startswith("/") or url.startswith("file://"):
        return True

    # HTTPS URL
    if re.match(r"^https?://[^\s/]+/[^\s]+", url):
        return True

    # SSH URL (git@host:path or ssh://...)
    if re.match(r"^git@[^\s:]+:[^\s]+", url):
        return True
    if re.match(r"^ssh://[^\s]+", url):
        return True

    return False


def verify_git_url_accessible(url: str) -> Tuple[bool, str]:
    """Try to access the git repository to verify it exists.

    Args:
        url: The git repository URL to verify.

    Returns:
        Tuple of (success, error_message). If success, error is empty.
    """
    try:
        result = subprocess.run(
            ["git", "ls-remote", "--exit-code", url],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return True, ""
        return (
            False,
            result.stderr.strip() or "Repository not found or not accessible",
        )
    except subprocess.TimeoutExpired:
        return False, "Connection timed out"
    except FileNotFoundError:
        return False, "git is not installed"
    except Exception as e:
        return False, str(e)
