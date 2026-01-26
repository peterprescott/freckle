"""Extended tests for ToolsRegistry - script installation and edge cases."""

import os
import subprocess
from unittest.mock import MagicMock, patch

from freckle.tools_registry import (
    PackageManager,
    ToolDefinition,
    ToolsRegistry,
)


class TestToolDefinitionIsInstalled:
    """Tests for ToolDefinition.is_installed method."""

    def test_uses_verify_command_when_provided(self):
        """Uses verify command when specified."""
        tool = ToolDefinition(
            name="mytool",
            verify="mytool --check"
        )

        with patch("freckle.tools_registry.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = tool.is_installed()

        assert result is True
        mock_run.assert_called_once()
        assert mock_run.call_args[0][0] == ["mytool", "--check"]

    def test_verify_command_failure(self):
        """Returns False when verify command fails."""
        tool = ToolDefinition(
            name="mytool",
            verify="mytool --check"
        )

        with patch("freckle.tools_registry.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(1, "mytool")
            result = tool.is_installed()

        assert result is False

    def test_verify_file_not_found(self):
        """Returns False when tool not found."""
        tool = ToolDefinition(
            name="mytool",
            verify="mytool --check"
        )

        with patch("freckle.tools_registry.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError()
            result = tool.is_installed()

        assert result is False

    def test_fallback_to_which(self):
        """Falls back to shutil.which when no verify command."""
        tool = ToolDefinition(name="git")

        with patch("freckle.tools_registry.shutil.which") as mock_which:
            mock_which.return_value = "/usr/bin/git"
            result = tool.is_installed()

        assert result is True

    def test_fallback_which_not_found(self):
        """Returns False when tool not in PATH."""
        tool = ToolDefinition(name="nonexistent")

        with patch("freckle.tools_registry.shutil.which") as mock_which:
            mock_which.return_value = None
            result = tool.is_installed()

        assert result is False


class TestToolDefinitionGetVersion:
    """Tests for ToolDefinition.get_version method."""

    def test_returns_version_with_version_flag(self):
        """Returns version when --version works."""
        tool = ToolDefinition(name="git")

        with patch("freckle.tools_registry.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="git version 2.39.0\n"
            )
            result = tool.get_version()

        assert result == "git version 2.39.0"

    def test_returns_none_on_all_flags_fail(self):
        """Returns None when all version flags fail."""
        tool = ToolDefinition(name="mytool")

        with patch("freckle.tools_registry.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError()
            result = tool.get_version()

        assert result is None

    def test_handles_timeout(self):
        """Handles timeout gracefully."""
        tool = ToolDefinition(name="mytool")

        with patch("freckle.tools_registry.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("mytool", 10)
            result = tool.get_version()

        assert result is None


class TestPackageManager:
    """Tests for PackageManager class."""

    def test_is_available_when_check_succeeds(self):
        """Returns True when check command succeeds."""
        pm = PackageManager(
            name="test",
            check_cmd=["true"],
            install_cmd=["test", "install"]
        )

        with patch("freckle.tools_registry.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = pm.is_available()

        assert result is True

    def test_is_available_when_check_fails(self):
        """Returns False when check command fails."""
        pm = PackageManager(
            name="test",
            check_cmd=["false"],
            install_cmd=["test", "install"]
        )

        with patch("freckle.tools_registry.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(1, "false")
            result = pm.is_available()

        assert result is False

    def test_is_available_when_not_found(self):
        """Returns False when command not found."""
        pm = PackageManager(
            name="test",
            check_cmd=["nonexistent"],
            install_cmd=["test", "install"]
        )

        with patch("freckle.tools_registry.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError()
            result = pm.is_available()

        assert result is False

    def test_install_success(self):
        """Returns True on successful install."""
        pm = PackageManager(
            name="brew",
            check_cmd=["brew", "--version"],
            install_cmd=["brew", "install"]
        )

        with patch("freckle.tools_registry.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = pm.install("git")

        assert result is True
        mock_run.assert_called_once()
        assert mock_run.call_args[0][0] == ["brew", "install", "git"]

    def test_install_with_sudo(self):
        """Prepends sudo when sudo_required is True."""
        pm = PackageManager(
            name="apt",
            check_cmd=["apt", "--version"],
            install_cmd=["apt", "install", "-y"],
            sudo_required=True
        )

        with patch("freckle.tools_registry.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            pm.install("git")

        args = mock_run.call_args[0][0]
        assert args[0] == "sudo"

    def test_install_failure(self):
        """Returns False on install failure."""
        pm = PackageManager(
            name="brew",
            check_cmd=["brew", "--version"],
            install_cmd=["brew", "install"]
        )

        with patch("freckle.tools_registry.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(1, "brew")
            result = pm.install("nonexistent")

        assert result is False


class TestToolsRegistryInstallViaScript:
    """Tests for _install_via_script method."""

    def test_requires_confirmation_env_var(self):
        """Returns False when confirmation env var not set."""
        registry = ToolsRegistry({})

        # Ensure env var is not set
        with patch.dict(os.environ, {}, clear=True):
            result = registry._install_via_script(
                "uv", "https://astral.sh/uv/install.sh", confirm=True
            )

        assert result is False

    def test_curl_failure_returns_false(self):
        """Returns False when curl fails."""
        registry = ToolsRegistry({})

        with patch.dict(os.environ, {"FRECKLE_CONFIRM_SCRIPTS": "1"}):
            with patch("freckle.tools_registry.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=1,
                    stderr="curl: connection refused"
                )
                result = registry._install_via_script(
                    "uv", "https://astral.sh/uv/install.sh", confirm=True
                )

        assert result is False

    def test_script_execution_failure_returns_false(self):
        """Returns False when script execution fails."""
        registry = ToolsRegistry({})

        with patch.dict(os.environ, {"FRECKLE_CONFIRM_SCRIPTS": "1"}):
            with patch("freckle.tools_registry.subprocess.run") as mock_run:
                mock_run.side_effect = [
                    # curl succeeds
                    MagicMock(returncode=0, stdout="#!/bin/sh\necho hello"),
                    # sh fails
                    subprocess.CalledProcessError(1, "sh"),
                ]
                result = registry._install_via_script(
                    "uv", "https://astral.sh/uv/install.sh", confirm=True
                )

        assert result is False

    def test_script_timeout_returns_false(self):
        """Returns False when script times out."""
        registry = ToolsRegistry({})

        with patch.dict(os.environ, {"FRECKLE_CONFIRM_SCRIPTS": "1"}):
            with patch("freckle.tools_registry.subprocess.run") as mock_run:
                mock_run.side_effect = [
                    # curl succeeds
                    MagicMock(returncode=0, stdout="#!/bin/sh\nsleep 999"),
                    # sh times out
                    subprocess.TimeoutExpired("sh", 300),
                ]
                result = registry._install_via_script(
                    "uv", "https://astral.sh/uv/install.sh", confirm=True
                )

        assert result is False

    def test_successful_script_installation(self):
        """Returns True on successful script installation."""
        registry = ToolsRegistry({})

        with patch.dict(os.environ, {"FRECKLE_CONFIRM_SCRIPTS": "1"}):
            with patch("freckle.tools_registry.subprocess.run") as mock_run:
                mock_run.side_effect = [
                    # curl succeeds
                    MagicMock(returncode=0, stdout="#!/bin/sh\necho done"),
                    # sh succeeds
                    MagicMock(returncode=0),
                ]
                result = registry._install_via_script(
                    "uv", "https://astral.sh/uv/install.sh", confirm=True
                )

        assert result is True


class TestToolsRegistryInstallTool:
    """Tests for install_tool method."""

    def test_no_available_package_manager(self):
        """Returns False when no package manager available."""
        registry = ToolsRegistry({})
        tool = ToolDefinition(
            name="mytool",
            install={"brew": "mytool", "apt": "mytool"}
        )

        # Mock all package managers as unavailable
        with patch(
            "freckle.tools_registry.PACKAGE_MANAGERS",
            {
                "brew": MagicMock(is_available=lambda: False),
                "apt": MagicMock(is_available=lambda: False),
            }
        ):
            result = registry.install_tool(tool)

        assert result is False

    def test_uses_first_available_manager(self):
        """Uses first available package manager in order."""
        registry = ToolsRegistry({})
        tool = ToolDefinition(
            name="git",
            install={"brew": "git", "apt": "git"}
        )

        mock_brew = MagicMock()
        mock_brew.is_available.return_value = True
        mock_brew.install.return_value = True

        with patch(
            "freckle.tools_registry.PACKAGE_MANAGERS",
            {"brew": mock_brew, "apt": MagicMock(is_available=lambda: False)}
        ):
            result = registry.install_tool(tool)

        assert result is True
        mock_brew.install.assert_called_once_with("git")

    def test_falls_back_to_next_manager(self):
        """Falls back to next manager if first fails."""
        registry = ToolsRegistry({})
        tool = ToolDefinition(
            name="mytool",
            install={"brew": "mytool", "apt": "mytool"}
        )

        mock_brew = MagicMock()
        mock_brew.is_available.return_value = True
        mock_brew.install.return_value = False  # Install fails

        mock_apt = MagicMock()
        mock_apt.is_available.return_value = True
        mock_apt.install.return_value = True

        with patch(
            "freckle.tools_registry.PACKAGE_MANAGERS",
            {"brew": mock_brew, "apt": mock_apt}
        ):
            result = registry.install_tool(tool)

        assert result is True
        mock_apt.install.assert_called_once()

    def test_falls_back_to_curated_script(self):
        """Falls back to curated script when package managers fail."""
        registry = ToolsRegistry({})
        tool = ToolDefinition(
            name="uv",
            install={"script": "uv"}
        )

        with patch.object(
            registry, "_install_via_script", return_value=True
        ) as mock_script:
            with patch(
                "freckle.tools_registry.PACKAGE_MANAGERS", {}
            ):
                result = registry.install_tool(tool)

        assert result is True
        mock_script.assert_called_once()

    def test_unknown_script_key_logs_warning(self):
        """Logs warning when script key not in curated registry."""
        registry = ToolsRegistry({})
        tool = ToolDefinition(
            name="mytool",
            install={"script": "unknown_script"}
        )

        with patch(
            "freckle.tools_registry.PACKAGE_MANAGERS", {}
        ):
            result = registry.install_tool(tool)

        assert result is False


class TestToolsRegistryHelpers:
    """Tests for helper methods."""

    def test_list_tools_returns_all_tools(self):
        """list_tools returns all configured tools."""
        registry = ToolsRegistry({
            "git": {"description": "Version control"},
            "vim": {"description": "Text editor"},
        })

        tools = registry.list_tools()

        assert len(tools) == 2
        names = [t.name for t in tools]
        assert "git" in names
        assert "vim" in names

    def test_get_tool_by_name(self):
        """get_tool returns specific tool."""
        registry = ToolsRegistry({
            "git": {"description": "Version control"},
        })

        tool = registry.get_tool("git")

        assert tool is not None
        assert tool.name == "git"

    def test_get_tool_nonexistent(self):
        """get_tool returns None for nonexistent tool."""
        registry = ToolsRegistry({})

        tool = registry.get_tool("nonexistent")

        assert tool is None

    def test_get_available_managers(self):
        """get_available_managers returns available managers."""
        with patch(
            "freckle.tools_registry.PACKAGE_MANAGERS",
            {
                "brew": MagicMock(is_available=lambda: True),
                "apt": MagicMock(is_available=lambda: False),
            }
        ):
            registry = ToolsRegistry({})
            managers = registry.get_available_managers()

        assert "brew" in managers
        assert "apt" not in managers
