"""Tests for secret detection."""

import tempfile
from pathlib import Path

from freckle.secrets import SecretScanner


class TestSecretScanner:
    """Tests for SecretScanner class."""

    def test_check_filename_ssh_key(self):
        """Detects SSH private key filenames."""
        scanner = SecretScanner()

        assert scanner.check_filename("id_rsa") is not None
        assert scanner.check_filename("id_ed25519") is not None
        assert scanner.check_filename(".ssh/id_rsa") is not None

    def test_check_filename_env_files(self):
        """Detects .env files."""
        scanner = SecretScanner()

        assert scanner.check_filename(".env") is not None
        assert scanner.check_filename(".env.local") is not None
        assert scanner.check_filename(".env.production") is not None
        assert scanner.check_filename("config.env") is not None

    def test_check_filename_credentials(self):
        """Detects credential files."""
        scanner = SecretScanner()

        assert scanner.check_filename(".aws/credentials") is not None
        assert scanner.check_filename("secret.yaml") is not None
        assert scanner.check_filename("api.token") is not None

    def test_check_filename_safe_files(self):
        """Does not flag safe files."""
        scanner = SecretScanner()

        assert scanner.check_filename(".zshrc") is None
        assert scanner.check_filename(".gitconfig") is None
        assert scanner.check_filename(".config/nvim/init.lua") is None

    def test_check_filename_allowed_files(self):
        """Does not flag explicitly allowed files."""
        scanner = SecretScanner()

        assert scanner.check_filename(".ssh/config") is None
        assert scanner.check_filename(".ssh/known_hosts") is None
        assert scanner.check_filename(".ssh/authorized_keys") is None

    def test_check_filename_extra_allow(self):
        """Respects extra allow patterns."""
        scanner = SecretScanner(extra_allow=[".env.example"])

        assert scanner.check_filename(".env") is not None
        assert scanner.check_filename(".env.example") is None

    def test_check_filename_extra_block(self):
        """Respects extra block patterns."""
        scanner = SecretScanner(extra_block=[r".*\.secret\.yaml$"])

        assert scanner.check_filename("config.secret.yaml") is not None
        assert scanner.check_filename("config.yaml") is None

    def test_check_content_private_key(self):
        """Detects private keys in content."""
        scanner = SecretScanner()

        content = """-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA0Z3...
-----END RSA PRIVATE KEY-----"""

        match = scanner.check_content("some_file", content)
        assert match is not None
        assert "private key" in match.reason.lower()

    def test_check_content_aws_key(self):
        """Detects AWS access keys in content."""
        scanner = SecretScanner()

        content = "aws_access_key_id = AKIAIOSFODNN7EXAMPLE"
        match = scanner.check_content("config", content)
        assert match is not None
        assert "AWS" in match.reason

    def test_check_content_github_token(self):
        """Detects GitHub tokens in content."""
        scanner = SecretScanner()

        content = "GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
        match = scanner.check_content("config", content)
        assert match is not None
        assert "GitHub" in match.reason

    def test_check_content_openai_key(self):
        """Detects OpenAI API keys in content."""
        scanner = SecretScanner()

        content = "OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"  # noqa: E501
        match = scanner.check_content("config", content)
        assert match is not None
        assert "OpenAI" in match.reason

    def test_check_content_password(self):
        """Detects passwords in content."""
        scanner = SecretScanner()

        content = 'password = "supersecretpassword123"'
        match = scanner.check_content("config", content)
        assert match is not None
        assert "password" in match.reason.lower()

    def test_check_content_safe_content(self):
        """Does not flag safe content."""
        scanner = SecretScanner()

        content = """
# My zsh configuration
export PATH="$HOME/bin:$PATH"
alias ll="ls -la"
"""
        match = scanner.check_content(".zshrc", content)
        assert match is None

    def test_check_content_allowed_file(self):
        """Returns None for explicitly allowed files."""
        scanner = SecretScanner()

        # .ssh/config is in DEFAULT_ALLOWED
        content = "password = supersecret123"
        match = scanner.check_content(".ssh/config", content)
        assert match is None

    def test_check_content_line_number(self):
        """Reports correct line number for matches."""
        scanner = SecretScanner()

        content = """line 1
line 2
password = "secret123456"
line 4"""

        match = scanner.check_content("config", content)
        assert match is not None
        assert match.line == 3

    def test_scan_file_with_real_file(self):
        """Scans actual file content."""
        scanner = SecretScanner()

        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            secret_file = home / "secret.key"
            secret_file.write_text("-----BEGIN PRIVATE KEY-----\nxxx\n")

            match = scanner.scan_file("secret.key", home)
            assert match is not None

    def test_scan_file_content_match_safe_filename(self):
        """Scans content when filename is safe but content has secret."""
        scanner = SecretScanner()

        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            # Safe filename but secret content
            config_file = home / "config.txt"
            config_file.write_text("-----BEGIN RSA PRIVATE KEY-----\nxxx\n")

            match = scanner.scan_file("config.txt", home)
            assert match is not None
            assert "private key" in match.reason.lower()

    def test_scan_file_handles_permission_error(self):
        """Handles permission errors gracefully."""
        scanner = SecretScanner()

        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            # Create a file that can't be read
            secret_file = home / "unreadable.txt"
            secret_file.write_text("content")
            secret_file.chmod(0o000)

            try:
                # Should not raise, just return None
                match = scanner.scan_file("unreadable.txt", home)
                # No filename pattern match, and content can't be read
                assert match is None
            finally:
                # Restore permissions for cleanup
                secret_file.chmod(0o644)

    def test_scan_file_without_home_skips_content(self):
        """Skips content check when home is None."""
        scanner = SecretScanner()

        # File with safe name, no home to read content
        match = scanner.scan_file("config.txt", home=None)
        assert match is None

    def test_scan_files_multiple(self):
        """Scans multiple files and returns all matches."""
        scanner = SecretScanner()

        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            (home / ".env").write_text("API_KEY=secret")
            (home / ".zshrc").write_text("export PATH=$PATH")
            (home / "id_rsa").write_text("-----BEGIN RSA PRIVATE KEY-----")

            matches = scanner.scan_files([".env", ".zshrc", "id_rsa"], home)
            assert len(matches) == 2  # .env and id_rsa

    def test_redact_snippet(self):
        """Redacts sensitive snippets."""
        scanner = SecretScanner()

        # Short strings
        assert "***" in scanner._redact_snippet("secret")

        # Longer strings show beginning and end
        result = scanner._redact_snippet("sk-verylongsecretkey123456")
        assert result.startswith("sk-ver")
        assert "..." in result


class TestSecretMatchDataclass:
    """Tests for SecretMatch dataclass."""

    def test_secret_match_basic(self):
        """Creates SecretMatch with required fields."""
        from freckle.secrets import SecretMatch

        match = SecretMatch(file=".env", reason="contains API key")
        assert match.file == ".env"
        assert match.reason == "contains API key"
        assert match.line is None
        assert match.snippet is None

    def test_secret_match_full(self):
        """Creates SecretMatch with all fields."""
        from freckle.secrets import SecretMatch

        match = SecretMatch(
            file=".env",
            reason="contains API key",
            line=5,
            snippet="API_KEY=sk-...",
        )
        assert match.line == 5
        assert match.snippet == "API_KEY=sk-..."
