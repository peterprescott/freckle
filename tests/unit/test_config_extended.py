"""Extended tests for Config class."""

from unittest.mock import MagicMock

import yaml

from freckle.config import Config


class TestConfigLoading:
    """Tests for Config loading."""

    def test_loads_from_path(self, tmp_path):
        """Loads config from path."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump({
            "dotfiles": {"repo_url": "https://github.com/user/dotfiles.git"}
        }))

        config = Config(config_path=config_file)

        assert config.get("dotfiles.repo_url") == (
            "https://github.com/user/dotfiles.git"
        )

    def test_nonexistent_path_uses_defaults(self, tmp_path):
        """Uses defaults when path doesn't exist."""
        config = Config(config_path=tmp_path / "nonexistent.yaml")

        assert config.get("dotfiles.dir") == "~/.dotfiles"

    def test_empty_config_uses_defaults(self, tmp_path):
        """Uses defaults when config file is empty."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("")

        config = Config(config_path=config_file)

        assert config.get("dotfiles.dir") == "~/.dotfiles"


class TestConfigDeepUpdate:
    """Tests for Config._deep_update method."""

    def test_deep_update_merges_nested_dicts(self, tmp_path):
        """Merges nested dictionaries."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump({
            "dotfiles": {"repo_url": "https://example.com/repo.git"}
        }))

        config = Config(config_path=config_file)

        # Should have merged, not replaced
        assert config.get("dotfiles.repo_url") == (
            "https://example.com/repo.git"
        )
        assert config.get("dotfiles.dir") == "~/.dotfiles"


class TestConfigApplyReplacements:
    """Tests for Config._apply_replacements method."""

    def test_replaces_local_user(self, tmp_path):
        """Replaces {local_user} with actual user."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump({
            "dotfiles": {"dir": "/home/{local_user}/.dotfiles"}
        }))

        mock_env = MagicMock()
        mock_env.user = "testuser"

        config = Config(config_path=config_file, env=mock_env)

        assert config.get("dotfiles.dir") == "/home/testuser/.dotfiles"

    def test_replaces_custom_vars(self, tmp_path):
        """Replaces custom vars."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump({
            "vars": {"myvar": "myvalue"},
            "dotfiles": {"dir": "/path/{myvar}/.dotfiles"}
        }))

        mock_env = MagicMock()
        mock_env.user = "user"

        config = Config(config_path=config_file, env=mock_env)

        assert config.get("dotfiles.dir") == "/path/myvalue/.dotfiles"

    def test_ignores_missing_vars(self, tmp_path):
        """Ignores missing replacement vars."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump({
            "dotfiles": {"dir": "/path/{unknown}/.dotfiles"}
        }))

        mock_env = MagicMock()
        mock_env.user = "user"

        config = Config(config_path=config_file, env=mock_env)

        # Should leave the string unchanged
        assert "{unknown}" in config.get("dotfiles.dir")


class TestConfigWalkAndFormat:
    """Tests for Config._walk_and_format with lists."""

    def test_formats_strings_in_lists(self, tmp_path):
        """Formats strings inside lists."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump({
            "vars": {"name": "test"},
            "secrets": {
                "block": ["/home/{local_user}/secrets", "{name}.key"]
            }
        }))

        mock_env = MagicMock()
        mock_env.user = "alice"

        config = Config(config_path=config_file, env=mock_env)

        block_list = config.get("secrets.block")
        assert "/home/alice/secrets" in block_list
        assert "test.key" in block_list

    def test_handles_nested_dicts_in_lists(self, tmp_path):
        """Handles nested dicts inside lists."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump({
            "vars": {"user": "bob"},
            "items": [
                {"path": "/home/{user}/file"},
                {"path": "/other/{user}/file"}
            ]
        }))

        mock_env = MagicMock()
        mock_env.user = "bob"

        config = Config(config_path=config_file, env=mock_env)

        items = config.get("items")
        assert items[0]["path"] == "/home/bob/file"
        assert items[1]["path"] == "/other/bob/file"

    def test_ignores_missing_vars_in_lists(self, tmp_path):
        """Ignores missing vars in list items."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump({
            "secrets": {
                "block": ["{unknown_var}/path", "normal/path"]
            }
        }))

        mock_env = MagicMock()
        mock_env.user = "user"

        config = Config(config_path=config_file, env=mock_env)

        block_list = config.get("secrets.block")
        assert "{unknown_var}/path" in block_list
        assert "normal/path" in block_list


class TestConfigGet:
    """Tests for Config.get method."""

    def test_get_nested_value(self, tmp_path):
        """Gets nested values with dot notation."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump({
            "dotfiles": {"repo_url": "https://example.com/repo.git"}
        }))

        config = Config(config_path=config_file)

        assert config.get("dotfiles.repo_url") == (
            "https://example.com/repo.git"
        )

    def test_get_returns_default_for_missing_key(self):
        """Returns default for missing keys."""
        config = Config()

        assert config.get("nonexistent.key") is None
        assert config.get("nonexistent.key", "default") == "default"

    def test_get_returns_default_for_invalid_path(self, tmp_path):
        """Returns default when path traverses non-dict."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump({
            "simple": "value"
        }))

        config = Config(config_path=config_file)

        # Trying to access simple.nested when simple is a string
        assert config.get("simple.nested") is None


class TestConfigProfiles:
    """Tests for Config profile methods."""

    def test_get_profiles(self, tmp_path):
        """Gets all profiles."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump({
            "profiles": {
                "work": {"modules": ["git", "vim"]},
                "home": {"modules": ["zsh"]}
            }
        }))

        config = Config(config_path=config_file)
        profiles = config.get_profiles()

        assert "work" in profiles
        assert "home" in profiles

    def test_get_profile(self, tmp_path):
        """Gets specific profile."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump({
            "profiles": {
                "work": {"modules": ["git", "vim"]}
            }
        }))

        config = Config(config_path=config_file)
        profile = config.get_profile("work")

        assert profile is not None
        assert profile["modules"] == ["git", "vim"]

    def test_get_profile_nonexistent(self, tmp_path):
        """Returns None for nonexistent profile."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump({
            "profiles": {"work": {}}
        }))

        config = Config(config_path=config_file)

        assert config.get_profile("nonexistent") is None

    def test_get_profile_branch(self, tmp_path):
        """Profile branch equals profile name."""
        config = Config()

        assert config.get_profile_branch("work") == "work"
        assert config.get_profile_branch("home") == "home"

    def test_get_profile_modules(self, tmp_path):
        """Gets modules for profile."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump({
            "profiles": {
                "work": {"modules": ["git", "vim"]}
            }
        }))

        config = Config(config_path=config_file)

        assert config.get_profile_modules("work") == ["git", "vim"]
        assert config.get_profile_modules("nonexistent") == []

    def test_list_profile_names(self, tmp_path):
        """Lists all profile names."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump({
            "profiles": {
                "work": {},
                "home": {},
                "server": {}
            }
        }))

        config = Config(config_path=config_file)
        names = config.list_profile_names()

        assert set(names) == {"work", "home", "server"}

    def test_get_branch_from_first_profile(self, tmp_path):
        """Gets branch from first profile."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump({
            "profiles": {
                "work": {},
                "home": {}
            }
        }))

        config = Config(config_path=config_file)
        branch = config.get_default_branch()

        # Should be one of the profile names
        assert branch in ["work", "home"]

    def test_get_branch_default_when_no_profiles(self):
        """Returns 'main' when no profiles."""
        config = Config()

        assert config.get_default_branch() == "main"

    def test_get_modules_from_first_profile(self, tmp_path):
        """Gets modules from first profile."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump({
            "profiles": {
                "work": {"modules": ["git", "vim"]}
            }
        }))

        config = Config(config_path=config_file)
        modules = config.get_modules()

        assert modules == ["git", "vim"]

    def test_get_modules_empty_when_no_profiles(self):
        """Returns empty list when no profiles."""
        config = Config()

        assert config.get_modules() == []
