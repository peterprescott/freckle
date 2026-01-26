"""Unit tests for the tools registry module."""

import subprocess
from unittest.mock import MagicMock, patch

from freckle.tools_registry import (
    CURATED_SCRIPTS,
    PackageManager,
    ToolDefinition,
    ToolsRegistry,
    get_tools_from_config,
)


class TestToolDefinition:
    """Tests for ToolDefinition class."""

    def test_from_dict_simple(self):
        """Test creating ToolDefinition from simple dict."""
        data = {
            "description": "Test tool",
            "install": {"brew": "test-tool"},
            "verify": "test-tool --version",
        }
        tool = ToolDefinition.from_dict("test", data)

        assert tool.name == "test"
        assert tool.description == "Test tool"
        assert tool.install == {"brew": "test-tool"}
        assert tool.verify == "test-tool --version"

    def test_from_dict_string_install(self):
        """Test creating ToolDefinition with string install."""
        data = {
            "description": "Simple tool",
            "install": "pkg-name",
        }
        tool = ToolDefinition.from_dict("simple", data)

        # String form should expand to brew and apt
        assert tool.install == {"brew": "pkg-name", "apt": "pkg-name"}

    def test_from_dict_with_config_files(self):
        """Test ToolDefinition with config files."""
        data = {
            "install": {"brew": "tool"},
            "config": [".config/tool/config.yml", ".toolrc"],
        }
        tool = ToolDefinition.from_dict("tool", data)

        assert tool.config_files == [".config/tool/config.yml", ".toolrc"]

    def test_from_dict_defaults(self):
        """Test ToolDefinition defaults."""
        data = {}
        tool = ToolDefinition.from_dict("minimal", data)

        assert tool.name == "minimal"
        assert tool.description == ""
        assert tool.install == {}
        assert tool.verify is None
        assert tool.config_files == []

    @patch("shutil.which")
    def test_is_installed_with_verify(self, mock_which):
        """Test is_installed uses verify command."""
        tool = ToolDefinition(
            name="test",
            verify="test-tool --version",
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            assert tool.is_installed() is True
            mock_run.assert_called_once()

    @patch("shutil.which")
    def test_is_installed_fallback_to_which(self, mock_which):
        """Test is_installed falls back to which."""
        tool = ToolDefinition(name="test-tool")

        mock_which.return_value = "/usr/bin/test-tool"
        assert tool.is_installed() is True
        mock_which.assert_called_with("test-tool")

        mock_which.return_value = None
        assert tool.is_installed() is False

    @patch("subprocess.run")
    def test_get_version(self, mock_run):
        """Test get_version extracts version string."""
        tool = ToolDefinition(name="test")

        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="test 1.2.3\nSome extra info",
        )

        version = tool.get_version()
        assert version == "test 1.2.3"


class TestPackageManager:
    """Tests for PackageManager class."""

    @patch("subprocess.run")
    def test_is_available_true(self, mock_run):
        """Test package manager availability check."""
        pm = PackageManager(
            name="brew",
            check_cmd=["brew", "--version"],
            install_cmd=["brew", "install"],
        )

        mock_run.return_value = MagicMock()
        assert pm.is_available() is True

    @patch("subprocess.run")
    def test_is_available_false(self, mock_run):
        """Test package manager not available."""
        pm = PackageManager(
            name="brew",
            check_cmd=["brew", "--version"],
            install_cmd=["brew", "install"],
        )

        mock_run.side_effect = FileNotFoundError()
        assert pm.is_available() is False

    @patch("subprocess.run")
    def test_install_success(self, mock_run):
        """Test successful package installation."""
        pm = PackageManager(
            name="brew",
            check_cmd=["brew", "--version"],
            install_cmd=["brew", "install"],
        )

        mock_run.return_value = MagicMock()
        assert pm.install("some-package") is True
        mock_run.assert_called_with(
            ["brew", "install", "some-package"],
            check=True,
            timeout=300,
        )

    @patch("subprocess.run")
    def test_install_with_sudo(self, mock_run):
        """Test installation with sudo."""
        pm = PackageManager(
            name="apt",
            check_cmd=["apt", "--version"],
            install_cmd=["apt", "install", "-y"],
            sudo_required=True,
        )

        mock_run.return_value = MagicMock()
        pm.install("some-package")

        # Should have sudo prepended
        mock_run.assert_called_with(
            ["sudo", "apt", "install", "-y", "some-package"],
            check=True,
            timeout=300,
        )

    @patch("subprocess.run")
    def test_install_failure(self, mock_run):
        """Test failed package installation."""
        pm = PackageManager(
            name="brew",
            check_cmd=["brew", "--version"],
            install_cmd=["brew", "install"],
        )

        mock_run.side_effect = subprocess.CalledProcessError(1, "brew")
        assert pm.install("bad-package") is False


class TestToolsRegistry:
    """Tests for ToolsRegistry class."""

    def test_init_from_config(self):
        """Test creating registry from config dict."""
        config = {
            "uv": {
                "description": "Python package manager",
                "install": {"brew": "uv", "script": "uv"},
                "verify": "uv --version",
            },
            "starship": {
                "description": "Shell prompt",
                "install": {"brew": "starship", "cargo": "starship"},
            },
        }

        registry = ToolsRegistry(config)

        assert len(registry.list_tools()) == 2
        assert registry.get_tool("uv") is not None
        assert registry.get_tool("starship") is not None
        assert registry.get_tool("nonexistent") is None

    def test_empty_registry(self):
        """Test empty registry."""
        registry = ToolsRegistry({})

        assert registry.list_tools() == []
        assert registry.get_tool("anything") is None

    @patch("freckle.tools_registry.PACKAGE_MANAGERS")
    def test_get_available_managers(self, mock_pms):
        """Test getting available package managers."""
        mock_brew = MagicMock()
        mock_brew.is_available.return_value = True

        mock_apt = MagicMock()
        mock_apt.is_available.return_value = False

        mock_pms.items.return_value = [
            ("brew", mock_brew),
            ("apt", mock_apt),
        ]

        registry = ToolsRegistry({})
        available = registry.get_available_managers()

        assert "brew" in available
        assert "apt" not in available


class TestCuratedScripts:
    """Tests for curated scripts registry."""

    def test_curated_scripts_exist(self):
        """Test that curated scripts are defined."""
        assert "uv" in CURATED_SCRIPTS
        assert "rustup" in CURATED_SCRIPTS
        assert "starship" in CURATED_SCRIPTS

    def test_curated_scripts_are_urls(self):
        """Test that curated scripts are valid URLs."""
        for name, url in CURATED_SCRIPTS.items():
            assert url.startswith("http"), f"{name} script should be a URL"


class TestGetToolsFromConfig:
    """Tests for get_tools_from_config helper."""

    def test_with_tools_section(self):
        """Test extracting tools from config."""
        mock_config = MagicMock()
        mock_config.data = {
            "tools": {
                "uv": {"install": {"brew": "uv"}},
            }
        }

        registry = get_tools_from_config(mock_config)
        assert len(registry.list_tools()) == 1

    def test_without_tools_section(self):
        """Test config without tools section."""
        mock_config = MagicMock()
        mock_config.data = {}

        registry = get_tools_from_config(mock_config)
        assert len(registry.list_tools()) == 0

    def test_with_invalid_tools_type(self):
        """Test config with non-dict tools section."""
        mock_config = MagicMock()
        mock_config.data = {"tools": ["list", "not", "dict"]}

        registry = get_tools_from_config(mock_config)
        assert len(registry.list_tools()) == 0
