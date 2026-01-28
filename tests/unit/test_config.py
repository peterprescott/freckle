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

    def test_get_profile_branch_equals_name(self):
        """Profile branch defaults to profile name."""
        config = Config()
        config.data["profiles"] = {
            "main": {"modules": ["zsh"]},
        }

        assert config.get_profile_branch("main") == "main"

    def test_get_profile_modules(self):
        """Gets modules for a profile (sorted)."""
        config = Config()
        config.data["profiles"] = {
            "main": {"modules": ["zsh", "nvim"]},
        }

        # Now returns sorted list for consistency
        assert config.get_profile_modules("main") == ["nvim", "zsh"]

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
        assert config.get_default_branch() == "main"

    def test_get_branch_defaults_to_main(self):
        """get_branch() defaults to 'main' when no profiles."""
        config = Config()
        assert config.get_default_branch() == "main"

    def test_get_modules_from_profile(self):
        """get_modules() returns first profile's modules (sorted)."""
        config = Config()
        config.data["profiles"] = {
            "main": {"modules": ["zsh", "nvim"]},
        }

        # Now returns sorted list for consistency
        assert config.get_modules() == ["nvim", "zsh"]

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


class TestResolveProfileModules:
    """Tests for profile module resolution with inheritance."""

    def test_no_includes_returns_direct_modules(self):
        """Profile without includes returns own modules as sorted set."""
        config = Config()
        config.data["profiles"] = {
            "main": {"modules": ["zsh", "git", "nvim"]},
        }

        modules, warnings = config.resolve_profile_modules("main")
        assert modules == {"zsh", "git", "nvim"}
        assert warnings == []

    def test_single_include_unions_modules(self):
        """Single include unions inherited and own modules."""
        config = Config()
        config.data["profiles"] = {
            "base": {"modules": ["git", "zsh"]},
            "mac": {"include": ["base"], "modules": ["karabiner"]},
        }

        modules, warnings = config.resolve_profile_modules("mac")
        assert modules == {"git", "zsh", "karabiner"}
        assert warnings == []

    def test_multiple_includes_unions_all(self):
        """Multiple includes union all inherited modules."""
        config = Config()
        config.data["profiles"] = {
            "shell": {"modules": ["zsh", "bash"]},
            "editor": {"modules": ["nvim", "vim"]},
            "full": {"include": ["shell", "editor"], "modules": ["tmux"]},
        }

        modules, warnings = config.resolve_profile_modules("full")
        assert modules == {"zsh", "bash", "nvim", "vim", "tmux"}

    def test_nested_includes_resolve_recursively(self):
        """Nested includes resolve recursively."""
        config = Config()
        config.data["profiles"] = {
            "base": {"modules": ["git"]},
            "mid": {"include": ["base"], "modules": ["zsh"]},
            "top": {"include": ["mid"], "modules": ["nvim"]},
        }

        modules, warnings = config.resolve_profile_modules("top")
        assert modules == {"git", "zsh", "nvim"}

    def test_diamond_inheritance_deduplicates(self):
        """Diamond inheritance naturally deduplicates via set union."""
        config = Config()
        config.data["profiles"] = {
            "base": {"modules": ["git"]},
            "dev": {"include": ["base"], "modules": ["nvim"]},
            "ops": {"include": ["base"], "modules": ["docker"]},
            "full": {"include": ["dev", "ops"], "modules": ["k8s"]},
        }

        modules, warnings = config.resolve_profile_modules("full")
        # git should appear only once
        assert modules == {"git", "nvim", "docker", "k8s"}

    def test_circular_dependency_raises(self):
        """Circular include raises ValueError."""
        import pytest

        config = Config()
        config.data["profiles"] = {
            "a": {"include": ["b"]},
            "b": {"include": ["a"]},
        }

        with pytest.raises(ValueError, match="Circular profile dependency"):
            config.resolve_profile_modules("a")

    def test_self_include_raises(self):
        """Including self raises ValueError."""
        import pytest

        config = Config()
        config.data["profiles"] = {
            "main": {"include": ["main"], "modules": ["git"]},
        }

        with pytest.raises(ValueError, match="cannot include itself"):
            config.resolve_profile_modules("main")

    def test_missing_include_warns_and_skips(self):
        """Including nonexistent profile warns but continues."""
        config = Config()
        config.data["profiles"] = {
            "main": {"include": ["nonexistent"], "modules": ["git"]},
        }

        modules, warnings = config.resolve_profile_modules("main")
        assert modules == {"git"}
        assert len(warnings) == 1
        assert "nonexistent" in warnings[0]

    def test_empty_include_list_allowed(self):
        """Empty include list is valid."""
        config = Config()
        config.data["profiles"] = {
            "main": {"include": [], "modules": ["git"]},
        }

        modules, warnings = config.resolve_profile_modules("main")
        assert modules == {"git"}
        assert warnings == []

    def test_include_without_modules_allowed(self):
        """Profile with include but no modules is valid."""
        config = Config()
        config.data["profiles"] = {
            "base": {"modules": ["git", "zsh"]},
            "alias": {"include": ["base"]},
        }

        modules, warnings = config.resolve_profile_modules("alias")
        assert modules == {"git", "zsh"}


class TestExcludeModules:
    """Tests for the exclude key."""

    def test_exclude_removes_inherited_modules(self):
        """Exclude removes modules from inherited set."""
        config = Config()
        config.data["profiles"] = {
            "base": {"modules": ["git", "zsh", "nvim"]},
            "minimal": {"include": ["base"], "exclude": ["nvim"]},
        }

        modules, _ = config.resolve_profile_modules("minimal")
        assert modules == {"git", "zsh"}

    def test_exclude_multiple_modules(self):
        """Can exclude multiple modules."""
        config = Config()
        config.data["profiles"] = {
            "base": {"modules": ["git", "zsh", "nvim", "tmux"]},
            "server": {
                "include": ["base"],
                "exclude": ["nvim", "tmux"],
                "modules": ["docker"],
            },
        }

        modules, _ = config.resolve_profile_modules("server")
        assert modules == {"git", "zsh", "docker"}

    def test_exclude_nonexistent_module_ignored(self):
        """Excluding module not in inherited set is no-op."""
        config = Config()
        config.data["profiles"] = {
            "base": {"modules": ["git"]},
            "child": {"include": ["base"], "exclude": ["nonexistent"]},
        }

        modules, _ = config.resolve_profile_modules("child")
        assert modules == {"git"}

    def test_exclude_without_include_no_effect(self):
        """Exclude with no include has no effect."""
        config = Config()
        config.data["profiles"] = {
            "main": {"exclude": ["git"], "modules": ["zsh"]},
        }

        modules, _ = config.resolve_profile_modules("main")
        assert modules == {"zsh"}

    def test_own_modules_added_after_exclude(self):
        """Own modules added after exclude, can re-add excluded."""
        config = Config()
        config.data["profiles"] = {
            "base": {"modules": ["git", "zsh"]},
            "child": {
                "include": ["base"],
                "exclude": ["git"],
                "modules": ["git"],  # Re-add git
            },
        }

        modules, _ = config.resolve_profile_modules("child")
        assert modules == {"git", "zsh"}

    def test_exclude_with_diamond_inheritance(self):
        """Exclude works correctly with diamond inheritance."""
        config = Config()
        config.data["profiles"] = {
            "base": {"modules": ["git", "common"]},
            "dev": {"include": ["base"], "modules": ["nvim"]},
            "ops": {"include": ["base"], "modules": ["docker"]},
            "server": {
                "include": ["dev", "ops"],
                "exclude": ["nvim", "common"],
                "modules": ["k8s"],
            },
        }

        modules, _ = config.resolve_profile_modules("server")
        assert modules == {"git", "docker", "k8s"}


class TestValidateProfileIncludes:
    """Tests for profile validation."""

    def test_valid_config_returns_no_errors(self):
        """Valid config returns empty errors list."""
        config = Config()
        config.data["profiles"] = {
            "base": {"modules": ["git"]},
            "mac": {"include": ["base"], "modules": ["karabiner"]},
        }

        errors, warnings = config.validate_profile_includes()
        assert errors == []

    def test_circular_dependency_is_error(self):
        """Circular dependency returned as error."""
        config = Config()
        config.data["profiles"] = {
            "a": {"include": ["b"]},
            "b": {"include": ["a"]},
        }

        errors, warnings = config.validate_profile_includes()
        assert len(errors) >= 1
        assert any("Circular" in e for e in errors)

    def test_self_include_is_error(self):
        """Self-include returned as error."""
        config = Config()
        config.data["profiles"] = {
            "main": {"include": ["main"], "modules": ["git"]},
        }

        errors, warnings = config.validate_profile_includes()
        assert len(errors) == 1
        assert "cannot include itself" in errors[0]

    def test_missing_include_is_warning(self):
        """Missing include returned as warning, not error."""
        config = Config()
        config.data["profiles"] = {
            "main": {"include": ["nonexistent"], "modules": ["git"]},
        }

        errors, warnings = config.validate_profile_includes()
        assert errors == []
        assert len(warnings) >= 1
        assert any("nonexistent" in w for w in warnings)

    def test_deep_inheritance_is_warning(self):
        """Inheritance depth > 3 returned as warning."""
        config = Config()
        config.data["profiles"] = {
            "l1": {"modules": ["a"]},
            "l2": {"include": ["l1"], "modules": ["b"]},
            "l3": {"include": ["l2"], "modules": ["c"]},
            "l4": {"include": ["l3"], "modules": ["d"]},
            "l5": {"include": ["l4"], "modules": ["e"]},
        }

        errors, warnings = config.validate_profile_includes()
        assert errors == []
        # l5 has depth 4, should warn
        assert any("deep inheritance" in w for w in warnings)


class TestGetProfileInheritanceDepth:
    """Tests for inheritance depth calculation."""

    def test_no_includes_returns_zero(self):
        """Profile with no includes has depth 0."""
        config = Config()
        config.data["profiles"] = {
            "main": {"modules": ["git"]},
        }

        assert config.get_profile_inheritance_depth("main") == 0

    def test_single_level_returns_one(self):
        """Single level of inheritance returns 1."""
        config = Config()
        config.data["profiles"] = {
            "base": {"modules": ["git"]},
            "child": {"include": ["base"]},
        }

        assert config.get_profile_inheritance_depth("child") == 1

    def test_nested_returns_max_depth(self):
        """Returns maximum depth across all include paths."""
        config = Config()
        config.data["profiles"] = {
            "l1": {"modules": ["a"]},
            "l2": {"include": ["l1"]},
            "l3": {"include": ["l2"]},
        }

        assert config.get_profile_inheritance_depth("l1") == 0
        assert config.get_profile_inheritance_depth("l2") == 1
        assert config.get_profile_inheritance_depth("l3") == 2


class TestGetProfileModulesWithInheritance:
    """Tests for get_profile_modules with inheritance."""

    def test_returns_sorted_list(self):
        """get_profile_modules returns sorted list for consistency."""
        config = Config()
        config.data["profiles"] = {
            "main": {"modules": ["zsh", "git", "nvim"]},
        }

        modules = config.get_profile_modules("main")
        assert modules == ["git", "nvim", "zsh"]  # Sorted

    def test_resolves_inheritance(self):
        """get_profile_modules resolves inherited modules."""
        config = Config()
        config.data["profiles"] = {
            "base": {"modules": ["git"]},
            "mac": {"include": ["base"], "modules": ["karabiner"]},
        }

        modules = config.get_profile_modules("mac")
        assert modules == ["git", "karabiner"]  # Sorted
