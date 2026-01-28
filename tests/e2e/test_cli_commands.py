"""End-to-end tests for CLI commands not covered elsewhere.

These tests ensure all CLI commands work correctly in real scenarios.
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


def _setup_mock_remote(tmp_path: Path, files: dict, branch: str = "main"):
    """Create a bare git repo with initial files."""
    remote_repo = tmp_path / "remote_dots.git"
    subprocess.run(
        ["git", "init", "--bare", str(remote_repo)],
        check=True,
        capture_output=True,
    )

    temp_worktree = tmp_path / "temp_worktree"
    temp_worktree.mkdir()
    subprocess.run(
        ["git", "init"], cwd=temp_worktree, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=temp_worktree,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=temp_worktree,
        check=True,
        capture_output=True,
    )

    for filename, content in files.items():
        file_path = temp_worktree / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)

    subprocess.run(
        ["git", "add", "."],
        cwd=temp_worktree,
        check=True,
        capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=temp_worktree,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "remote", "add", "origin", str(remote_repo)],
        cwd=temp_worktree,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "push", "origin", f"HEAD:{branch}"],
        cwd=temp_worktree,
        check=True,
        capture_output=True,
    )

    return remote_repo


def _init_freckle(home: Path, remote_repo: Path, env: dict):
    """Initialize freckle with a remote repo (init now clones automatically)."""
    init_input = f"y\n{remote_repo}\nmain\n.dotfiles\n"
    subprocess.run(
        ["uv", "run", "freckle", "init"],
        input=init_input,
        text=True,
        env=env,
        capture_output=True,
        check=True,
        timeout=30,
    )


class TestVersionCommand:
    """Tests for the version command."""

    def test_version_shows_version(self, tmp_path):
        """Version command shows version string."""
        home = tmp_path / "fake_home"
        home.mkdir()
        env = _create_env(home)

        result = subprocess.run(
            ["uv", "run", "freckle", "version"],
            env=env,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        # Should show a version number or "(development)"
        assert "freckle" in result.stdout.lower() or "." in result.stdout


class TestHistoryCommand:
    """Tests for the history command."""

    def test_history_shows_commits(self, tmp_path):
        """History command shows commit history."""
        home = tmp_path / "fake_home"
        home.mkdir()
        env = _create_env(home)

        remote = _setup_mock_remote(tmp_path, {".zshrc": "# zshrc"})
        _init_freckle(home, remote, env)

        result = subprocess.run(
            ["uv", "run", "freckle", "history"],
            env=env,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "init" in result.stdout.lower() or "commit" in result.stdout

    def test_history_oneline(self, tmp_path):
        """History --oneline shows compact format."""
        home = tmp_path / "fake_home"
        home.mkdir()
        env = _create_env(home)

        remote = _setup_mock_remote(tmp_path, {".zshrc": "# zshrc"})
        _init_freckle(home, remote, env)

        result = subprocess.run(
            ["uv", "run", "freckle", "history", "--oneline"],
            env=env,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0

    def test_history_without_init_fails(self, tmp_path):
        """History fails when not initialized."""
        home = tmp_path / "fake_home"
        home.mkdir()
        env = _create_env(home)

        result = subprocess.run(
            ["uv", "run", "freckle", "history"],
            env=env,
            capture_output=True,
            text=True,
        )

        assert result.returncode != 0


class TestChangesCommand:
    """Tests for the changes command."""

    def test_changes_no_changes(self, tmp_path):
        """Changes shows no changes when clean."""
        home = tmp_path / "fake_home"
        home.mkdir()
        env = _create_env(home)

        remote = _setup_mock_remote(tmp_path, {".zshrc": "# zshrc"})
        _init_freckle(home, remote, env)

        result = subprocess.run(
            ["uv", "run", "freckle", "changes"],
            env=env,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "no" in result.stdout.lower()

    def test_changes_shows_changes(self, tmp_path):
        """Changes shows uncommitted changes."""
        home = tmp_path / "fake_home"
        home.mkdir()
        env = _create_env(home)

        remote = _setup_mock_remote(tmp_path, {".zshrc": "# zshrc"})
        _init_freckle(home, remote, env)

        # Modify a file
        (home / ".zshrc").write_text("# modified zshrc\nalias ll='ls -la'")

        result = subprocess.run(
            ["uv", "run", "freckle", "changes"],
            env=env,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        # Should show the diff
        assert "modified" in result.stdout or "+" in result.stdout

    def test_changes_without_init_fails(self, tmp_path):
        """Changes fails when not initialized."""
        home = tmp_path / "fake_home"
        home.mkdir()
        env = _create_env(home)

        result = subprocess.run(
            ["uv", "run", "freckle", "changes"],
            env=env,
            capture_output=True,
            text=True,
        )

        assert result.returncode != 0


class TestUntrackCommand:
    """Tests for the untrack command."""

    def test_untrack_stops_tracking(self, tmp_path):
        """Untrack stops tracking a file but keeps it."""
        home = tmp_path / "fake_home"
        home.mkdir()
        env = _create_env(home)

        remote = _setup_mock_remote(tmp_path, {".zshrc": "# zshrc"})
        _init_freckle(home, remote, env)

        # Verify file is tracked
        assert (home / ".zshrc").exists()

        result = subprocess.run(
            ["uv", "run", "freckle", "untrack", ".zshrc"],
            env=env,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "stopped tracking" in result.stdout.lower()
        # File should still exist
        assert (home / ".zshrc").exists()

    def test_untrack_without_init_fails(self, tmp_path):
        """Untrack fails when not initialized."""
        home = tmp_path / "fake_home"
        home.mkdir()
        env = _create_env(home)

        result = subprocess.run(
            ["uv", "run", "freckle", "untrack", ".zshrc"],
            env=env,
            capture_output=True,
            text=True,
        )

        assert result.returncode != 0


class TestFetchCommand:
    """Tests for the fetch command."""

    def test_fetch_already_up_to_date(self, tmp_path):
        """Fetch shows up-to-date message when no changes."""
        home = tmp_path / "fake_home"
        home.mkdir()
        env = _create_env(home)

        remote = _setup_mock_remote(tmp_path, {".zshrc": "# zshrc"})
        _init_freckle(home, remote, env)

        result = subprocess.run(
            ["uv", "run", "freckle", "fetch"],
            env=env,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "up-to-date" in result.stdout.lower()

    def test_fetch_with_local_changes_prompts(self, tmp_path):
        """Fetch prompts when there are unsaved local changes."""
        home = tmp_path / "fake_home"
        home.mkdir()
        env = _create_env(home)

        remote = _setup_mock_remote(tmp_path, {".zshrc": "# zshrc"})
        _init_freckle(home, remote, env)

        # Modify a file
        (home / ".zshrc").write_text("# modified")

        result = subprocess.run(
            ["uv", "run", "freckle", "fetch"],
            env=env,
            capture_output=True,
            text=True,
        )

        assert result.returncode != 0
        out = result.stdout.lower()
        assert "unsaved" in out or "local changes" in out

    def test_fetch_without_init_fails(self, tmp_path):
        """Fetch fails when not initialized."""
        home = tmp_path / "fake_home"
        home.mkdir()
        env = _create_env(home)

        result = subprocess.run(
            ["uv", "run", "freckle", "fetch"],
            env=env,
            capture_output=True,
            text=True,
        )

        assert result.returncode != 0


class TestProfileCommands:
    """Tests for profile subcommands."""

    def test_profile_list(self, tmp_path):
        """Profile list shows available profiles."""
        home = tmp_path / "fake_home"
        home.mkdir()
        env = _create_env(home)

        remote = _setup_mock_remote(tmp_path, {".zshrc": "# zshrc"})
        _init_freckle(home, remote, env)

        result = subprocess.run(
            ["uv", "run", "freckle", "profile", "list"],
            env=env,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0

    def test_profile_show(self, tmp_path):
        """Profile show shows current profile."""
        home = tmp_path / "fake_home"
        home.mkdir()
        env = _create_env(home)

        remote = _setup_mock_remote(tmp_path, {".zshrc": "# zshrc"})
        _init_freckle(home, remote, env)

        result = subprocess.run(
            ["uv", "run", "freckle", "profile", "show"],
            env=env,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "main" in result.stdout.lower()

    def test_profile_create(self, tmp_path):
        """Profile create creates a new profile."""
        home = tmp_path / "fake_home"
        home.mkdir()
        env = _create_env(home)

        remote = _setup_mock_remote(tmp_path, {".zshrc": "# zshrc"})
        _init_freckle(home, remote, env)

        result = subprocess.run(
            ["uv", "run", "freckle", "profile", "create", "work"],
            env=env,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        out_lower = result.stdout.lower()
        assert "work" in out_lower or "created" in out_lower

    def test_profile_switch_nonexistent(self, tmp_path):
        """Profile switch to nonexistent profile fails."""
        home = tmp_path / "fake_home"
        home.mkdir()
        env = _create_env(home)

        remote = _setup_mock_remote(tmp_path, {".zshrc": "# zshrc"})
        _init_freckle(home, remote, env)

        result = subprocess.run(
            ["uv", "run", "freckle", "profile", "switch", "nonexistent"],
            env=env,
            capture_output=True,
            text=True,
        )

        assert result.returncode != 0

    def test_profile_diff(self, tmp_path):
        """Profile diff shows differences between profiles."""
        home = tmp_path / "fake_home"
        home.mkdir()
        env = _create_env(home)

        remote = _setup_mock_remote(tmp_path, {".zshrc": "# zshrc"})
        _init_freckle(home, remote, env)

        # Create another profile first
        subprocess.run(
            ["uv", "run", "freckle", "profile", "create", "work"],
            env=env,
            capture_output=True,
        )

        result = subprocess.run(
            ["uv", "run", "freckle", "profile", "diff", "work"],
            env=env,
            capture_output=True,
            text=True,
        )

        # Should succeed (may show no diff if identical)
        assert result.returncode == 0

    def test_profile_delete_requires_name(self, tmp_path):
        """Profile delete requires a name."""
        home = tmp_path / "fake_home"
        home.mkdir()
        env = _create_env(home)

        remote = _setup_mock_remote(tmp_path, {".zshrc": "# zshrc"})
        _init_freckle(home, remote, env)

        result = subprocess.run(
            ["uv", "run", "freckle", "profile", "delete"],
            env=env,
            capture_output=True,
            text=True,
        )

        assert result.returncode != 0


class TestRestoreCommand:
    """Tests for the restore command."""

    def test_restore_list_empty(self, tmp_path):
        """Restore --list shows no restore points initially."""
        home = tmp_path / "fake_home"
        home.mkdir()
        env = _create_env(home)

        result = subprocess.run(
            ["uv", "run", "freckle", "restore", "--list"],
            env=env,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        out_lower = result.stdout.lower()
        assert "no restore points" in out_lower

    def test_restore_without_identifier_fails(self, tmp_path):
        """Restore without identifier shows usage."""
        home = tmp_path / "fake_home"
        home.mkdir()
        env = _create_env(home)

        result = subprocess.run(
            ["uv", "run", "freckle", "restore"],
            env=env,
            capture_output=True,
            text=True,
        )

        assert result.returncode != 0
        assert "usage" in result.stderr.lower()

    def test_restore_nonexistent_point_fails(self, tmp_path):
        """Restore with nonexistent point fails."""
        home = tmp_path / "fake_home"
        home.mkdir()
        env = _create_env(home)

        result = subprocess.run(
            ["uv", "run", "freckle", "restore", "2099-01-01"],
            env=env,
            capture_output=True,
            text=True,
        )

        assert result.returncode != 0
        assert "not found" in result.stderr.lower()


class TestScheduleCommand:
    """Tests for the schedule command."""

    def test_schedule_status(self, tmp_path):
        """Schedule without args shows status."""
        home = tmp_path / "fake_home"
        home.mkdir()
        env = _create_env(home)

        result = subprocess.run(
            ["uv", "run", "freckle", "schedule"],
            env=env,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        out_lower = result.stdout.lower()
        # Either shows schedule or says not configured
        assert "schedule" in out_lower or "configured" in out_lower

    def test_schedule_invalid_frequency(self, tmp_path):
        """Schedule with invalid frequency fails."""
        home = tmp_path / "fake_home"
        home.mkdir()
        env = _create_env(home)

        result = subprocess.run(
            ["uv", "run", "freckle", "schedule", "monthly"],
            env=env,
            capture_output=True,
            text=True,
        )

        assert result.returncode != 0
        assert "invalid" in result.stderr.lower()


class TestConfigCommand:
    """Tests for the config command."""

    def test_config_check_no_profiles(self, tmp_path):
        """Config check handles no profiles gracefully."""
        home = tmp_path / "fake_home"
        home.mkdir()
        env = _create_env(home)

        result = subprocess.run(
            ["uv", "run", "freckle", "config", "check"],
            env=env,
            capture_output=True,
            text=True,
        )

        # Should say no profiles configured
        assert "no profiles" in result.stdout.lower()

    def test_config_without_subcommand_needs_config(self, tmp_path):
        """Config without subcommand fails if no config exists."""
        home = tmp_path / "fake_home"
        home.mkdir()
        env = _create_env(home)

        result = subprocess.run(
            ["uv", "run", "freckle", "config"],
            env=env,
            capture_output=True,
            text=True,
        )

        # Should fail because config doesn't exist
        assert result.returncode != 0
        assert "not found" in result.stdout.lower()


class TestToolsCommand:
    """Tests for the tools command."""

    def test_tools_list(self, tmp_path):
        """Tools list shows configured tools."""
        home = tmp_path / "fake_home"
        home.mkdir()
        env = _create_env(home)

        # Create config with tools
        config = home / ".freckle.yaml"
        config.write_text("""
dotfiles:
  repo_url: test
  branch: main
  dir: .dotfiles
tools:
  git:
    description: Version control
    verify: git --version
""")

        result = subprocess.run(
            ["uv", "run", "freckle", "tools"],
            env=env,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "git" in result.stdout.lower()
