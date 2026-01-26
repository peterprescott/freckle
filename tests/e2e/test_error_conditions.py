"""End-to-end tests for error conditions and edge cases.

These tests verify that freckle handles error conditions gracefully
with appropriate error messages and exit codes.
"""

import os
import subprocess
from pathlib import Path


def _create_env(home: Path) -> dict:
    """Create environment variables for tests."""
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["USER"] = "testuser"
    env["FRECKLE_MOCK_PKGS"] = "1"
    return env


class TestMissingConfig:
    """Tests for when no config file exists."""

    def test_sync_without_init_fails(self, tmp_path):
        """Sync fails gracefully when no config exists."""
        home = tmp_path / "fake_home"
        home.mkdir()
        env = _create_env(home)

        result = subprocess.run(
            ["uv", "run", "freckle", "sync"],
            env=env,
            capture_output=True,
            text=True,
        )

        assert result.returncode != 0
        stderr_lower = result.stderr.lower()
        assert "freckle init" in stderr_lower or "no" in stderr_lower

    def test_backup_without_init_fails(self, tmp_path):
        """Backup fails gracefully when no config exists."""
        home = tmp_path / "fake_home"
        home.mkdir()
        env = _create_env(home)

        result = subprocess.run(
            ["uv", "run", "freckle", "backup"],
            env=env,
            capture_output=True,
            text=True,
        )

        assert result.returncode != 0

    def test_status_without_init_shows_not_configured(self, tmp_path):
        """Status shows 'not configured' when no config exists."""
        home = tmp_path / "fake_home"
        home.mkdir()
        env = _create_env(home)

        result = subprocess.run(
            ["uv", "run", "freckle", "status"],
            env=env,
            capture_output=True,
            text=True,
        )

        # Status shows informative message even without config
        stdout_lower = result.stdout.lower()
        assert "not found" in stdout_lower or "not configured" in stdout_lower


class TestInvalidConfig:
    """Tests for invalid configuration files."""

    def test_invalid_yaml_syntax(self, tmp_path):
        """Freckle handles invalid YAML syntax gracefully."""
        home = tmp_path / "fake_home"
        home.mkdir()
        env = _create_env(home)

        # Create invalid YAML
        config_path = home / ".freckle.yaml"
        config_path.write_text("invalid: yaml: syntax: [unclosed")

        result = subprocess.run(
            ["uv", "run", "freckle", "sync"],
            env=env,
            capture_output=True,
            text=True,
        )

        assert result.returncode != 0

    def test_missing_dotfiles_section(self, tmp_path):
        """Freckle handles missing dotfiles section gracefully."""
        home = tmp_path / "fake_home"
        home.mkdir()
        env = _create_env(home)

        # Create config without dotfiles section
        config_path = home / ".freckle.yaml"
        config_path.write_text("profiles:\n  main:\n    modules: [zsh]")

        result = subprocess.run(
            ["uv", "run", "freckle", "sync"],
            env=env,
            capture_output=True,
            text=True,
        )

        assert result.returncode != 0


class TestDoctorChecks:
    """Tests for the doctor command."""

    def test_doctor_reports_missing_config(self, tmp_path):
        """Doctor reports missing config file."""
        home = tmp_path / "fake_home"
        home.mkdir()
        env = _create_env(home)

        result = subprocess.run(
            ["uv", "run", "freckle", "doctor"],
            env=env,
            capture_output=True,
            text=True,
        )

        # Should report issues but still run
        output = result.stdout.lower() + result.stderr.lower()
        assert "config" in output

    def test_doctor_reports_missing_repo(self, tmp_path):
        """Doctor reports missing dotfiles repo."""
        home = tmp_path / "fake_home"
        home.mkdir()
        env = _create_env(home)

        # Create valid config but no repo
        config_path = home / ".freckle.yaml"
        config_path.write_text(
            "dotfiles:\n"
            "  repo_url: https://example.com/dots.git\n"
            "  branch: main\n"
            "  dir: .dotfiles\n"
        )

        result = subprocess.run(
            ["uv", "run", "freckle", "doctor"],
            env=env,
            capture_output=True,
            text=True,
        )

        # Should report repo not found
        assert result.returncode != 0 or "not" in result.stdout.lower()


class TestProfileErrors:
    """Tests for profile command error conditions."""

    def test_switch_nonexistent_profile(self, tmp_path):
        """Switching to nonexistent profile fails gracefully."""
        home = tmp_path / "fake_home"
        home.mkdir()
        env = _create_env(home)

        # Create config with profiles
        config_path = home / ".freckle.yaml"
        config_path.write_text(
            "dotfiles:\n"
            "  repo_url: https://example.com/dots.git\n"
            "  branch: main\n"
            "  dir: .dotfiles\n"
            "profiles:\n"
            "  main:\n"
            "    modules: [zsh]\n"
        )

        result = subprocess.run(
            ["uv", "run", "freckle", "profile", "switch", "nonexistent"],
            env=env,
            capture_output=True,
            text=True,
        )

        assert result.returncode != 0
        assert "not found" in result.stderr.lower()


class TestInitErrors:
    """Tests for init command error conditions."""

    def test_init_with_existing_config_fails(self, tmp_path):
        """Init fails when config already exists (without --force)."""
        home = tmp_path / "fake_home"
        home.mkdir()
        env = _create_env(home)

        # Create existing config
        config_path = home / ".freckle.yaml"
        config_path.write_text("dotfiles:\n  repo_url: test\n")

        result = subprocess.run(
            ["uv", "run", "freckle", "init"],
            env=env,
            capture_output=True,
            text=True,
            input="n\n",  # Answer no to any prompts
        )

        assert result.returncode != 0
        stderr_lower = result.stderr.lower()
        assert "exists" in stderr_lower or "force" in stderr_lower
