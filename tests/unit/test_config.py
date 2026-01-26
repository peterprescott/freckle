"""Tests for Config class."""

from freckle.config import Config


class TestConfigDefaults:
    """Tests for default configuration."""

    def test_config_defaults(self):
        """Default config has expected structure."""
        config = Config()
        assert config.get("dotfiles.repo_url") is None
        assert config.get("dotfiles.dir") == "~/.dotfiles"
        assert config.get("profiles") == {}
        assert config.get("tools") == {}

    def test_config_has_secrets_defaults(self):
        """Default config includes secrets section."""
        config = Config()
        assert config.get("secrets.block") == []
        assert config.get("secrets.allow") == []


class TestConfigProfiles:
    """Tests for profile-related config methods."""

    def test_get_profiles(self):
        """Gets all profile definitions."""
        config = Config()
        config.data["profiles"] = {
            "main": {"modules": ["zsh"]},
            "work": {"modules": ["nvim"]},
        }

        profiles = config.get_profiles()
        assert "main" in profiles
        assert "work" in profiles

    def test_get_profile(self):
        """Gets a specific profile."""
        config = Config()
        config.data["profiles"] = {
            "main": {"description": "Main", "modules": ["zsh"]},
        }

        profile = config.get_profile("main")
        assert profile["description"] == "Main"
        assert profile["modules"] == ["zsh"]

    def test_get_profile_nonexistent(self):
        """Returns None for nonexistent profile."""
        config = Config()
        assert config.get_profile("nonexistent") is None

    def test_get_profile_branch_explicit(self):
        """Gets explicit branch from profile."""
        config = Config()
        config.data["profiles"] = {
            "work": {"branch": "work-laptop", "modules": []},
        }

        assert config.get_profile_branch("work") == "work-laptop"

    def test_get_profile_branch_defaults_to_name(self):
        """Profile branch defaults to profile name."""
        config = Config()
        config.data["profiles"] = {
            "main": {"modules": ["zsh"]},
        }

        assert config.get_profile_branch("main") == "main"

    def test_get_profile_modules(self):
        """Gets modules for a profile."""
        config = Config()
        config.data["profiles"] = {
            "main": {"modules": ["zsh", "nvim"]},
        }

        assert config.get_profile_modules("main") == ["zsh", "nvim"]

    def test_list_profile_names(self):
        """Lists all profile names."""
        config = Config()
        config.data["profiles"] = {
            "main": {},
            "work": {},
            "server": {},
        }

        names = config.list_profile_names()
        assert "main" in names
        assert "work" in names
        assert "server" in names


class TestConfigBranchAndModules:
    """Tests for branch and module accessor methods."""

    def test_get_branch_from_profile(self):
        """get_branch() returns first profile's branch."""
        config = Config()
        config.data["profiles"] = {
            "main": {"branch": "main"},
            "work": {"branch": "work"},
        }

        # Should return first profile's branch
        assert config.get_branch() == "main"

    def test_get_branch_defaults_to_main(self):
        """get_branch() defaults to 'main' when no profiles."""
        config = Config()
        assert config.get_branch() == "main"

    def test_get_modules_from_profile(self):
        """get_modules() returns first profile's modules."""
        config = Config()
        config.data["profiles"] = {
            "main": {"modules": ["zsh", "nvim"]},
        }

        assert config.get_modules() == ["zsh", "nvim"]

    def test_get_modules_empty_when_no_profiles(self):
        """get_modules() returns empty list when no profiles."""
        config = Config()
        assert config.get_modules() == []


class TestConfigTemplating:
    """Tests for config templating."""

    def test_config_templating(self, mocker):
        """Templates are replaced with values."""
        mock_env = mocker.Mock()
        mock_env.user = "testuser"

        user_config = {
            "dotfiles": {
                "repo_url": "https://github.com/{local_user}/dots.git"
            }
        }

        config = Config(env=mock_env)
        config._deep_update(config.data, user_config)
        config._apply_replacements(config.data)

        assert (
            config.get("dotfiles.repo_url")
            == "https://github.com/testuser/dots.git"
        )

    def test_custom_vars(self, mocker):
        """Custom vars are available in templates."""
        mock_env = mocker.Mock()
        mock_env.user = "localuser"

        user_config = {
            "vars": {"git_host": "gitlab.com", "git_user": "gituser"},
            "dotfiles": {"repo_url": "https://{git_host}/{git_user}/repo.git"},
        }

        config = Config(env=mock_env)
        config._deep_update(config.data, user_config)
        config._apply_replacements(config.data)

        assert (
            config.get("dotfiles.repo_url")
            == "https://gitlab.com/gituser/repo.git"
        )


class TestConfigDeepMerge:
    """Tests for deep merge functionality."""

    def test_deep_merge(self):
        """Deep merge preserves nested defaults."""
        config = Config()
        update = {
            "dotfiles": {"repo_url": "https://..."},
            "profiles": {"main": {"modules": ["zsh"]}},
        }
        config._deep_update(config.data, update)

        assert config.get("dotfiles.repo_url") == "https://..."
        assert config.get("dotfiles.dir") == "~/.dotfiles"  # Preserved
        assert config.get("profiles.main.modules") == ["zsh"]
