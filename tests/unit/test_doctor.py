"""Tests for doctor command and its helper functions."""

from unittest.mock import MagicMock

from freckle.cli.doctor import (
    _check_config,
    _check_prerequisites,
    _diff_configs,
    _get_config_from_branch,
    _get_latest_version,
    _print_suggestions,
)


class TestGetLatestVersion:
    """Tests for _get_latest_version function."""

    def test_returns_version_on_success(self, mocker):
        """Returns version string from PyPI response."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"info": {"version": "1.2.3"}}'
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        mocker.patch(
            "freckle.cli.doctor.urllib.request.urlopen",
            return_value=mock_response,
        )

        result = _get_latest_version()
        assert result == "1.2.3"

    def test_returns_none_on_network_error(self, mocker):
        """Returns None when network request fails."""
        mocker.patch(
            "freckle.cli.doctor.urllib.request.urlopen",
            side_effect=Exception("Network error"),
        )

        result = _get_latest_version()
        assert result is None

    def test_returns_none_on_invalid_json(self, mocker):
        """Returns None when response is not valid JSON."""
        mock_response = MagicMock()
        mock_response.read.return_value = b"not valid json"
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        mocker.patch(
            "freckle.cli.doctor.urllib.request.urlopen",
            return_value=mock_response,
        )

        result = _get_latest_version()
        assert result is None


class TestCheckPrerequisites:
    """Tests for _check_prerequisites function."""

    def test_returns_empty_when_git_available(self, mocker):
        """Returns no issues when git is installed."""
        mocker.patch("freckle.cli.doctor.is_git_available", return_value=True)

        issues = _check_prerequisites(verbose=False)

        assert issues == []

    def test_returns_issue_when_git_missing(self, mocker):
        """Returns issue when git is not installed."""
        mocker.patch("freckle.cli.doctor.is_git_available", return_value=False)

        issues = _check_prerequisites(verbose=False)

        assert "git is not installed" in issues


class TestCheckConfig:
    """Tests for _check_config function."""

    def test_returns_issue_when_no_config(self, mocker, tmp_path):
        """Returns issue when config file doesn't exist."""
        mocker.patch(
            "freckle.cli.doctor.CONFIG_PATH",
            tmp_path / ".freckle.yaml",
        )

        issues, warnings = _check_config(verbose=False)

        assert any("Missing" in i for i in issues)

    def test_returns_no_issues_for_valid_config(self, mocker, tmp_path):
        """Returns no issues for valid config file."""
        config_path = tmp_path / ".freckle.yaml"
        config_path.write_text("dotfiles:\n  repo_url: https://example.com")

        mocker.patch("freckle.cli.doctor.CONFIG_PATH", config_path)

        issues, warnings = _check_config(verbose=False)

        assert issues == []

    def test_warns_on_unknown_keys(self, mocker, tmp_path):
        """Warns about unknown configuration keys."""
        config_path = tmp_path / ".freckle.yaml"
        config_path.write_text(
            "dotfiles:\n  repo_url: https://example.com\n"
            "unknown_key: value\n"
        )

        mocker.patch("freckle.cli.doctor.CONFIG_PATH", config_path)

        issues, warnings = _check_config(verbose=False)

        assert any("unknown_key" in w for w in warnings)


class TestGetConfigFromBranch:
    """Tests for _get_config_from_branch function."""

    def test_returns_config_content_for_yaml(self):
        """Returns config content when .freckle.yaml exists."""
        mock_dotfiles = MagicMock()
        mock_result = MagicMock()
        mock_result.stdout = "dotfiles:\n  repo_url: test"
        mock_dotfiles._git.run.return_value = mock_result

        content = _get_config_from_branch(mock_dotfiles, "main")

        assert content == "dotfiles:\n  repo_url: test"
        mock_dotfiles._git.run.assert_called_with(
            "show", "main:.freckle.yaml"
        )

    def test_tries_yml_extension_on_yaml_failure(self):
        """Falls back to .yml when .yaml doesn't exist."""
        from subprocess import CalledProcessError

        mock_dotfiles = MagicMock()
        mock_result = MagicMock()
        mock_result.stdout = "dotfiles:\n  repo_url: test"

        def side_effect(cmd, path):
            if path == "main:.freckle.yaml":
                raise CalledProcessError(1, "git")
            return mock_result

        mock_dotfiles._git.run.side_effect = side_effect

        content = _get_config_from_branch(mock_dotfiles, "main")

        assert content == "dotfiles:\n  repo_url: test"

    def test_returns_none_when_no_config(self):
        """Returns None when neither config file exists."""
        from subprocess import CalledProcessError

        mock_dotfiles = MagicMock()
        mock_dotfiles._git.run.side_effect = CalledProcessError(1, "git")

        content = _get_config_from_branch(mock_dotfiles, "main")

        assert content is None


class TestDiffConfigs:
    """Tests for _diff_configs function."""

    def test_detects_missing_profiles(self):
        """Detects profiles in current but not in other."""
        current = "profiles:\n  main: {}\n  work: {}"
        other = "profiles:\n  main: {}"

        diff = _diff_configs(current, other)

        assert "work" in diff.missing_profiles
        assert not diff.extra_profiles

    def test_detects_extra_profiles(self):
        """Detects profiles in other but not in current."""
        current = "profiles:\n  main: {}"
        other = "profiles:\n  main: {}\n  work: {}"

        diff = _diff_configs(current, other)

        assert "work" in diff.extra_profiles
        assert not diff.missing_profiles

    def test_detects_missing_tools(self):
        """Detects tools in current but not in other."""
        current = "tools:\n  nvim: {}\n  zsh: {}"
        other = "tools:\n  nvim: {}"

        diff = _diff_configs(current, other)

        assert "zsh" in diff.missing_tools
        assert not diff.extra_tools

    def test_detects_extra_tools(self):
        """Detects tools in other but not in current."""
        current = "tools:\n  nvim: {}"
        other = "tools:\n  nvim: {}\n  zsh: {}"

        diff = _diff_configs(current, other)

        assert "zsh" in diff.extra_tools
        assert not diff.missing_tools

    def test_no_differences_when_identical(self):
        """Returns empty diff when configs are identical."""
        config = "profiles:\n  main: {}\ntools:\n  nvim: {}"

        diff = _diff_configs(config, config)

        assert not diff.has_differences()

    def test_handles_empty_configs(self):
        """Handles empty or minimal configs gracefully."""
        diff = _diff_configs("", "profiles:\n  main: {}")

        assert "main" in diff.extra_profiles

    def test_handles_invalid_yaml(self):
        """Returns empty diff for invalid YAML."""
        diff = _diff_configs("not: valid: yaml:", "also: invalid: yaml:")

        assert not diff.has_differences()


class TestPrintSuggestions:
    """Tests for _print_suggestions function."""

    def test_suggests_upgrade_for_version_warning(self, capsys):
        """Suggests upgrade when version warning is present."""
        warnings = ["Freckle 1.0.0 available (you have 0.9.0)"]

        _print_suggestions([], warnings)

        captured = capsys.readouterr()
        assert "freckle upgrade" in captured.out

    def test_suggests_init_for_missing_config(self, capsys):
        """Suggests init when config is missing."""
        issues = ["Missing /home/user/.freckle.yaml"]

        _print_suggestions(issues, [])

        captured = capsys.readouterr()
        assert "freckle init" in captured.out

    def test_suggests_save_for_uncommitted_changes(self, capsys):
        """Suggests save for uncommitted changes."""
        warnings = ["5 uncommitted changes"]

        _print_suggestions([], warnings)

        captured = capsys.readouterr()
        assert "freckle save" in captured.out

    def test_suggests_fetch_for_behind_remote(self, capsys):
        """Suggests fetch when behind remote."""
        warnings = ["3 commits behind remote"]

        _print_suggestions([], warnings)

        captured = capsys.readouterr()
        assert "freckle fetch" in captured.out

    def test_deduplicates_suggestions(self, capsys):
        """Does not print duplicate suggestions."""
        warnings = [
            "Freckle 1.0.0 available (you have 0.9.0)",
            "Freckle 1.1.0 available (you have 0.9.0)",  # Same suggestion
        ]

        _print_suggestions([], warnings)

        captured = capsys.readouterr()
        # Should only appear once
        assert captured.out.count("freckle upgrade") == 1
