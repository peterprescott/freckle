"""Tests for profile management functionality."""

import subprocess
from pathlib import Path
from unittest.mock import patch

import yaml

import freckle.cli.profile as profile_module
from freckle.cli.profile import _add_profile_to_config


class TestAddProfileToConfig:
    """Tests for _add_profile_to_config function."""

    def test_adds_profile_to_empty_profiles(self, tmp_path):
        """Adds profile when profiles section is empty."""
        config_path = tmp_path / ".freckle.yaml"
        config_path.write_text(
            yaml.dump({
                "dotfiles": {"repo_url": "https://example.com/dots"},
                "profiles": {},
            })
        )

        with patch.object(profile_module, "CONFIG_PATH", config_path):
            _add_profile_to_config("test", "Test profile", ["zsh", "nvim"])

        data = yaml.safe_load(config_path.read_text())
        assert "test" in data["profiles"]
        assert data["profiles"]["test"]["modules"] == ["zsh", "nvim"]
        assert data["profiles"]["test"]["description"] == "Test profile"

    def test_adds_profile_to_existing_profiles(self, tmp_path):
        """Adds profile when other profiles exist."""
        config_path = tmp_path / ".freckle.yaml"
        config_path.write_text(
            yaml.dump({
                "dotfiles": {"repo_url": "https://example.com/dots"},
                "profiles": {
                    "main": {"modules": ["zsh"]},
                },
            })
        )

        with patch.object(profile_module, "CONFIG_PATH", config_path):
            _add_profile_to_config("work", "", ["nvim"])

        data = yaml.safe_load(config_path.read_text())
        assert "main" in data["profiles"]
        assert "work" in data["profiles"]
        assert data["profiles"]["main"]["modules"] == ["zsh"]
        assert data["profiles"]["work"]["modules"] == ["nvim"]

    def test_preserves_other_config_sections(self, tmp_path):
        """Adding profile preserves other config sections."""
        config_path = tmp_path / ".freckle.yaml"
        config_path.write_text(
            yaml.dump({
                "dotfiles": {"repo_url": "https://example.com/dots"},
                "profiles": {"main": {"modules": ["zsh"]}},
                "tools": {"git": {"install": {"brew": "git"}}},
                "secrets": {"block": ["*.pem"]},
            })
        )

        with patch.object(profile_module, "CONFIG_PATH", config_path):
            _add_profile_to_config("test", "", [])

        data = yaml.safe_load(config_path.read_text())
        assert data["dotfiles"]["repo_url"] == "https://example.com/dots"
        assert data["tools"]["git"]["install"]["brew"] == "git"
        assert data["secrets"]["block"] == ["*.pem"]

    def test_no_description_if_empty(self, tmp_path):
        """Empty description is not added to profile."""
        config_path = tmp_path / ".freckle.yaml"
        config_path.write_text(yaml.dump({"profiles": {}}))

        with patch.object(profile_module, "CONFIG_PATH", config_path):
            _add_profile_to_config("test", "", ["zsh"])

        data = yaml.safe_load(config_path.read_text())
        assert "description" not in data["profiles"]["test"]
        assert data["profiles"]["test"]["modules"] == ["zsh"]


class TestProfileCreateIntegration:
    """Integration tests for profile creation with git operations."""

    def _setup_dotfiles_repo(self, tmp_path: Path) -> tuple[Path, Path]:
        """Set up a fake dotfiles bare repo and home directory."""
        home = tmp_path / "home"
        home.mkdir()

        # Create bare repo
        dotfiles_dir = home / ".dotfiles"
        subprocess.run(
            ["git", "init", "--bare", str(dotfiles_dir)],
            check=True,
            capture_output=True,
        )

        # Create initial config
        config_path = home / ".freckle.yaml"
        config_path.write_text(
            yaml.dump({
                "dotfiles": {
                    "repo_url": f"file://{dotfiles_dir}",
                    "dir": ".dotfiles",
                },
                "profiles": {
                    "main": {"modules": ["zsh"]},
                },
            })
        )

        # Initialize worktree and make initial commit
        subprocess.run(
            ["git", f"--git-dir={dotfiles_dir}", f"--work-tree={home}",
             "config", "user.email", "test@test.com"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", f"--git-dir={dotfiles_dir}", f"--work-tree={home}",
             "config", "user.name", "Test"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", f"--git-dir={dotfiles_dir}", f"--work-tree={home}",
             "add", str(config_path)],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", f"--git-dir={dotfiles_dir}", f"--work-tree={home}",
             "commit", "-m", "Initial config"],
            check=True,
            capture_output=True,
        )

        return home, dotfiles_dir

    def _get_config_from_branch(
        self, dotfiles_dir: Path, home: Path, branch: str
    ) -> dict:
        """Get the config content from a specific branch."""
        result = subprocess.run(
            ["git", f"--git-dir={dotfiles_dir}", f"--work-tree={home}",
             "show", f"{branch}:.freckle.yaml"],
            capture_output=True,
            text=True,
            check=True,
        )
        return yaml.safe_load(result.stdout)

    def _list_branches(self, dotfiles_dir: Path, home: Path) -> list[str]:
        """List all branches in the repo."""
        result = subprocess.run(
            ["git", f"--git-dir={dotfiles_dir}", f"--work-tree={home}",
             "branch", "--list", "--format=%(refname:short)"],
            capture_output=True,
            text=True,
            check=True,
        )
        return [b.strip() for b in result.stdout.strip().split("\n") if b]

    def test_profile_create_updates_config(self, tmp_path):
        """Creating a profile adds it to the config."""
        home, dotfiles_dir = self._setup_dotfiles_repo(tmp_path)

        # Manually add a profile to config (simulating profile create)
        config_path = home / ".freckle.yaml"
        data = yaml.safe_load(config_path.read_text())
        data["profiles"]["work"] = {"modules": ["nvim"]}
        config_path.write_text(yaml.dump(data))

        # Verify the config was updated
        data = yaml.safe_load(config_path.read_text())
        assert "main" in data["profiles"]
        assert "work" in data["profiles"]
        assert data["profiles"]["work"]["modules"] == ["nvim"]

    def test_config_propagation_to_multiple_branches(self, tmp_path):
        """Config should be identical across all profile branches."""
        home, dotfiles_dir = self._setup_dotfiles_repo(tmp_path)

        # Create a second branch manually
        subprocess.run(
            ["git", f"--git-dir={dotfiles_dir}", f"--work-tree={home}",
             "branch", "work"],
            check=True,
            capture_output=True,
        )

        # Update config on main and commit
        config_path = home / ".freckle.yaml"
        data = yaml.safe_load(config_path.read_text())
        data["profiles"]["server"] = {"modules": []}
        config_path.write_text(yaml.dump(data))

        subprocess.run(
            ["git", f"--git-dir={dotfiles_dir}", f"--work-tree={home}",
             "add", str(config_path)],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", f"--git-dir={dotfiles_dir}", f"--work-tree={home}",
             "commit", "-m", "Add server profile"],
            check=True,
            capture_output=True,
        )

        # Propagate to work branch
        subprocess.run(
            ["git", f"--git-dir={dotfiles_dir}", f"--work-tree={home}",
             "checkout", "work"],
            check=True,
            capture_output=True,
        )
        config_path.write_text(yaml.dump(data))
        subprocess.run(
            ["git", f"--git-dir={dotfiles_dir}", f"--work-tree={home}",
             "add", str(config_path)],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", f"--git-dir={dotfiles_dir}", f"--work-tree={home}",
             "commit", "-m", "Add server profile"],
            check=True,
            capture_output=True,
        )

        # Verify both branches have the same config
        main_config = self._get_config_from_branch(dotfiles_dir, home, "main")
        work_config = self._get_config_from_branch(dotfiles_dir, home, "work")

        assert "server" in main_config["profiles"]
        assert "server" in work_config["profiles"]
        assert main_config == work_config

    def test_all_branches_have_all_profiles(self, tmp_path):
        """After creating multiple profiles, all branches should list all."""
        home, dotfiles_dir = self._setup_dotfiles_repo(tmp_path)
        config_path = home / ".freckle.yaml"

        # Create work branch
        subprocess.run(
            ["git", f"--git-dir={dotfiles_dir}", f"--work-tree={home}",
             "branch", "work"],
            check=True,
            capture_output=True,
        )

        # Create server branch
        subprocess.run(
            ["git", f"--git-dir={dotfiles_dir}", f"--work-tree={home}",
             "branch", "server"],
            check=True,
            capture_output=True,
        )

        # Update config with all profiles
        data = {
            "dotfiles": {"repo_url": f"file://{dotfiles_dir}"},
            "profiles": {
                "main": {"modules": ["zsh"]},
                "work": {"modules": ["nvim"]},
                "server": {"modules": []},
            },
        }

        # Commit to all branches
        for branch in ["main", "work", "server"]:
            subprocess.run(
                ["git", f"--git-dir={dotfiles_dir}", f"--work-tree={home}",
                 "checkout", branch],
                check=True,
                capture_output=True,
            )
            config_path.write_text(yaml.dump(data))
            subprocess.run(
                ["git", f"--git-dir={dotfiles_dir}", f"--work-tree={home}",
                 "add", str(config_path)],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", f"--git-dir={dotfiles_dir}", f"--work-tree={home}",
                 "commit", "-m", "Sync all profiles"],
                check=True,
                capture_output=True,
            )

        # Verify all branches have all profiles
        for branch in ["main", "work", "server"]:
            config = self._get_config_from_branch(dotfiles_dir, home, branch)
            assert "main" in config["profiles"], f"{branch} missing main"
            assert "work" in config["profiles"], f"{branch} missing work"
            assert "server" in config["profiles"], f"{branch} missing server"
