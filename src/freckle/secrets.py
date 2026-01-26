"""Secret detection for dotfiles.

Prevents accidentally committing secrets like SSH keys, API tokens, and
credentials to the dotfiles repository.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class SecretMatch:
    """A detected secret in a file."""

    file: str
    reason: str
    line: Optional[int] = None
    snippet: Optional[str] = None


# Filename patterns that indicate secrets (case-insensitive)
SECRET_FILENAME_PATTERNS: list[str] = [
    # SSH keys
    r"^id_rsa$",
    r"^id_ed25519$",
    r"^id_ecdsa$",
    r"^id_dsa$",
    r".*\.pem$",
    r".*\.key$",
    # Environment files
    r"^\.env$",
    r"^\.env\..*$",
    r".*\.env$",
    # Credentials
    r".*credentials.*",
    r".*secret.*",
    r".*\.token$",
    # Specific files
    r"^\.netrc$",
    r"^\.npmrc$",
    r"^\.pypirc$",
]

# Content patterns that indicate secrets
SECRET_CONTENT_PATTERNS: list[tuple[str, str]] = [
    # Private keys
    (r"-----BEGIN[A-Z ]*PRIVATE KEY-----", "private key"),
    (r"-----BEGIN RSA PRIVATE KEY-----", "RSA private key"),
    (r"-----BEGIN OPENSSH PRIVATE KEY-----", "OpenSSH private key"),
    # AWS
    (r"AKIA[0-9A-Z]{16}", "AWS access key"),
    (r"aws_secret_access_key\s*=", "AWS secret key"),
    # Common patterns
    (r"(?i)api[_-]?key\s*[=:]\s*['\"]?[a-z0-9]{20,}", "API key"),
    (r"(?i)api[_-]?secret\s*[=:]\s*['\"]?[a-z0-9]{20,}", "API secret"),
    (r"(?i)password\s*[=:]\s*['\"]?[^\s'\"]{8,}", "password"),
    (r"(?i)secret\s*[=:]\s*['\"]?[a-z0-9]{20,}", "secret value"),
    # Tokens
    (r"ghp_[a-zA-Z0-9]{36}", "GitHub personal access token"),
    (r"gho_[a-zA-Z0-9]{36}", "GitHub OAuth token"),
    (r"github_pat_[a-zA-Z0-9]{22}_[a-zA-Z0-9]{59}", "GitHub PAT"),
    (r"sk-[a-zA-Z0-9]{48}", "OpenAI API key"),
    (r"sk-proj-[a-zA-Z0-9-_]{100,}", "OpenAI project key"),
]

# Default allowed files (match patterns but are safe)
DEFAULT_ALLOWED: list[str] = [
    ".ssh/config",
    ".ssh/known_hosts",
    ".ssh/authorized_keys",
]


class SecretScanner:
    """Scans files for potential secrets."""

    def __init__(
        self,
        extra_block: Optional[list[str]] = None,
        extra_allow: Optional[list[str]] = None,
    ):
        """Initialize scanner with optional extra patterns.

        Args:
            extra_block: Additional filename patterns to block
            extra_allow: Additional files to allow despite matching patterns
        """
        self.filename_patterns = [
            re.compile(p, re.IGNORECASE) for p in SECRET_FILENAME_PATTERNS
        ]
        if extra_block:
            self.filename_patterns.extend(
                re.compile(p, re.IGNORECASE) for p in extra_block
            )

        self.content_patterns = [
            (re.compile(p), desc) for p, desc in SECRET_CONTENT_PATTERNS
        ]

        self.allowed = set(DEFAULT_ALLOWED)
        if extra_allow:
            self.allowed.update(extra_allow)

    def is_allowed(self, filepath: str) -> bool:
        """Check if a file is explicitly allowed."""
        return filepath in self.allowed

    def check_filename(self, filepath: str) -> Optional[SecretMatch]:
        """Check if filename matches secret patterns.

        Args:
            filepath: Path relative to home directory

        Returns:
            SecretMatch if file appears to be a secret, None otherwise
        """
        if self.is_allowed(filepath):
            return None

        filename = Path(filepath).name

        for pattern in self.filename_patterns:
            if pattern.match(filename):
                return SecretMatch(
                    file=filepath,
                    reason=f"filename matches secret pattern: {pattern.pattern}",  # noqa: E501
                )

        return None

    def check_content(
        self, filepath: str, content: str
    ) -> Optional[SecretMatch]:
        """Check if file content contains secret patterns.

        Args:
            filepath: Path relative to home directory
            content: File content to scan

        Returns:
            SecretMatch if content appears to contain secrets, None otherwise
        """
        if self.is_allowed(filepath):
            return None

        for pattern, description in self.content_patterns:
            match = pattern.search(content)
            if match:
                # Find line number
                line_num = content[: match.start()].count("\n") + 1
                # Get snippet (redacted)
                snippet = self._redact_snippet(match.group(0))
                return SecretMatch(
                    file=filepath,
                    reason=f"contains {description}",
                    line=line_num,
                    snippet=snippet,
                )

        return None

    def scan_file(
        self, filepath: str, home: Optional[Path] = None
    ) -> Optional[SecretMatch]:
        """Scan a file for secrets (filename and content).

        Args:
            filepath: Path relative to home directory
            home: Home directory path (for reading file content)

        Returns:
            SecretMatch if file appears to contain secrets, None otherwise
        """
        # Check filename first (fast)
        match = self.check_filename(filepath)
        if match:
            return match

        # Check content if file exists and is readable
        if home:
            full_path = home / filepath
            if full_path.is_file():
                try:
                    content = full_path.read_text(errors="ignore")
                    match = self.check_content(filepath, content)
                    if match:
                        return match
                except (OSError, PermissionError):
                    pass  # Can't read file, skip content check

        return None

    def scan_files(
        self, filepaths: list[str], home: Optional[Path] = None
    ) -> list[SecretMatch]:
        """Scan multiple files for secrets.

        Args:
            filepaths: Paths relative to home directory
            home: Home directory path (for reading file content)

        Returns:
            List of SecretMatch objects for files with detected secrets
        """
        matches = []
        for filepath in filepaths:
            match = self.scan_file(filepath, home)
            if match:
                matches.append(match)
        return matches

    def _redact_snippet(self, text: str, max_len: int = 40) -> str:
        """Redact a snippet to avoid exposing the actual secret."""
        if len(text) <= 10:
            return text[:3] + "***"
        # Show first 6 and last 4 chars
        if len(text) > max_len:
            text = text[:max_len]
        return text[:6] + "..." + text[-4:]
