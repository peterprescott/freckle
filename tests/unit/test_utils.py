"""Tests for utility functions."""

import logging
import subprocess
from unittest.mock import MagicMock, patch

from freckle.utils import (
    get_version,
    setup_logging,
    validate_git_url,
    verify_git_url_accessible,
)


class TestSetupLogging:
    """Tests for setup_logging function."""

    def test_verbose_mode_runs_without_error(self):
        """Verbose mode runs without error."""
        # basicConfig only works once, so we just verify no exception
        setup_logging(verbose=True)

    def test_non_verbose_mode_runs_without_error(self):
        """Non-verbose mode runs without error."""
        setup_logging(verbose=False)


class TestGetVersion:
    """Tests for get_version function."""

    def test_returns_version_when_installed(self):
        """Returns version string when package is installed."""
        version = get_version()
        # Should return something (either version or development)
        assert isinstance(version, str)
        assert len(version) > 0

    def test_returns_development_when_not_installed(self):
        """Returns '(development)' when package not found."""
        with patch("freckle.utils.importlib.metadata.version") as mock:
            import importlib.metadata
            mock.side_effect = importlib.metadata.PackageNotFoundError()
            version = get_version()
            assert version == "(development)"


class TestValidateGitUrl:
    """Tests for validate_git_url function."""

    def test_empty_url_returns_false(self):
        """Empty URL is invalid."""
        assert validate_git_url("") is False

    def test_none_url_returns_false(self):
        """None URL is invalid."""
        assert validate_git_url(None) is False

    def test_local_path_is_valid(self):
        """Local absolute paths are valid."""
        assert validate_git_url("/path/to/repo") is True
        assert validate_git_url("/home/user/.dotfiles") is True

    def test_file_protocol_is_valid(self):
        """file:// URLs are valid."""
        assert validate_git_url("file:///path/to/repo") is True

    def test_https_url_is_valid(self):
        """HTTPS URLs are valid."""
        assert validate_git_url("https://github.com/user/repo.git") is True
        assert validate_git_url("https://gitlab.com/user/repo") is True
        assert validate_git_url("http://example.com/repo.git") is True

    def test_ssh_url_is_valid(self):
        """SSH URLs are valid."""
        assert validate_git_url("git@github.com:user/repo.git") is True
        assert validate_git_url("git@gitlab.com:org/project.git") is True

    def test_ssh_protocol_url_is_valid(self):
        """ssh:// protocol URLs are valid."""
        assert validate_git_url("ssh://git@github.com/user/repo.git") is True

    def test_invalid_url_returns_false(self):
        """Invalid URLs return False."""
        assert validate_git_url("not-a-url") is False
        assert validate_git_url("ftp://example.com/repo") is False
        assert validate_git_url("random string") is False


class TestVerifyGitUrlAccessible:
    """Tests for verify_git_url_accessible function."""

    def test_accessible_repo_returns_success(self):
        """Accessible repository returns (True, '')."""
        with patch("freckle.utils.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            success, error = verify_git_url_accessible(
                "https://github.com/user/repo.git"
            )
            assert success is True
            assert error == ""

    def test_inaccessible_repo_returns_error(self):
        """Inaccessible repository returns (False, message)."""
        with patch("freckle.utils.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=128,
                stderr="fatal: repository not found"
            )
            success, error = verify_git_url_accessible(
                "https://github.com/user/nonexistent.git"
            )
            assert success is False
            err_lower = error.lower()
            assert "repository" in err_lower or "not found" in err_lower

    def test_timeout_returns_error(self):
        """Timeout returns appropriate error."""
        with patch("freckle.utils.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(
                cmd="git", timeout=30
            )
            success, error = verify_git_url_accessible(
                "https://slow-server.com/repo.git"
            )
            assert success is False
            assert "timed out" in error.lower()

    def test_git_not_installed_returns_error(self):
        """Missing git returns appropriate error."""
        with patch("freckle.utils.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError()
            success, error = verify_git_url_accessible(
                "https://github.com/user/repo.git"
            )
            assert success is False
            assert "git" in error.lower()

    def test_generic_exception_returns_error(self):
        """Generic exception returns error message."""
        with patch("freckle.utils.subprocess.run") as mock_run:
            mock_run.side_effect = Exception("Something went wrong")
            success, error = verify_git_url_accessible(
                "https://github.com/user/repo.git"
            )
            assert success is False
            assert "Something went wrong" in error
