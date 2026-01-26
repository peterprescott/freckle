"""Tests for system module."""

import platform
from pathlib import Path
from unittest.mock import mock_open, patch

from freckle.system import OS, Environment


class TestOS:
    """Tests for OS enum."""

    def test_os_values(self):
        """OS enum has correct values."""
        assert OS.LINUX.value == "linux"
        assert OS.MACOS.value == "macos"
        assert OS.UNKNOWN.value == "unknown"


class TestEnvironmentDetectOS:
    """Tests for Environment._detect_os method."""

    def test_detect_linux(self):
        """Detects Linux correctly."""
        with patch.object(platform, "system", return_value="Linux"):
            env = Environment()
            assert env.os == OS.LINUX

    def test_detect_macos(self):
        """Detects macOS correctly."""
        with patch.object(platform, "system", return_value="Darwin"):
            env = Environment()
            assert env.os == OS.MACOS

    def test_detect_unknown(self):
        """Detects unknown OS correctly."""
        with patch.object(platform, "system", return_value="Windows"):
            env = Environment()
            assert env.os == OS.UNKNOWN


class TestEnvironmentOSInfo:
    """Tests for Environment._get_os_info method."""

    def test_linux_with_os_release(self, tmp_path):
        """Gets distro info from /etc/os-release on Linux."""
        os_release_content = """PRETTY_NAME="Ubuntu 22.04.1 LTS"
ID=ubuntu
VERSION_ID="22.04"
"""
        with patch.object(platform, "system", return_value="Linux"):
            with patch.object(
                Path, "exists", return_value=True
            ):
                with patch(
                    "builtins.open",
                    mock_open(read_data=os_release_content)
                ):
                    env = Environment()

        assert env.os_info["pretty_name"] == "Ubuntu 22.04.1 LTS"
        assert env.os_info["distro"] == "ubuntu"
        assert env.os_info["distro_version"] == "22.04"

    def test_linux_without_os_release(self):
        """Falls back when /etc/os-release doesn't exist."""
        with patch.object(platform, "system", return_value="Linux"):
            with patch.object(Path, "exists", return_value=False):
                env = Environment()

        assert env.os_info["pretty_name"] == "Linux"

    def test_macos_info(self):
        """Gets macOS version info."""
        with patch.object(platform, "system", return_value="Darwin"):
            with patch.object(
                platform, "mac_ver", return_value=("14.0", ("", "", ""), "")
            ):
                env = Environment()

        assert "macOS 14.0" in env.os_info["pretty_name"]
        assert env.os_info["distro"] == "macos"
        assert env.os_info["distro_version"] == "14.0"


class TestEnvironmentUser:
    """Tests for Environment user detection."""

    def test_user_from_env_user(self):
        """Gets user from USER env var."""
        with patch.dict("os.environ", {"USER": "testuser", "LOGNAME": ""}):
            env = Environment()
            assert env.user == "testuser"

    def test_user_from_logname(self):
        """Falls back to LOGNAME env var."""
        with patch.dict(
            "os.environ", {"USER": "", "LOGNAME": "loguser"}, clear=True
        ):
            env = Environment()
            # Either loguser or fallback to home name
            assert env.user in ["loguser", env.home.name]

    def test_user_fallback_to_home(self):
        """Falls back to home directory name."""
        with patch.dict("os.environ", {}, clear=True):
            # Remove USER and LOGNAME
            import os
            orig_user = os.environ.pop("USER", None)
            orig_logname = os.environ.pop("LOGNAME", None)
            try:
                env = Environment()
                assert env.user == env.home.name
            finally:
                if orig_user:
                    os.environ["USER"] = orig_user
                if orig_logname:
                    os.environ["LOGNAME"] = orig_logname


class TestEnvironmentHelpers:
    """Tests for Environment helper methods."""

    def test_is_linux(self):
        """is_linux returns True on Linux."""
        with patch.object(platform, "system", return_value="Linux"):
            env = Environment()
            assert env.is_linux() is True
            assert env.is_macos() is False

    def test_is_macos(self):
        """is_macos returns True on macOS."""
        with patch.object(platform, "system", return_value="Darwin"):
            env = Environment()
            assert env.is_macos() is True
            assert env.is_linux() is False

    def test_repr(self):
        """__repr__ returns expected format."""
        env = Environment()
        repr_str = repr(env)

        assert "Environment(" in repr_str
        assert "os=" in repr_str
        assert "home=" in repr_str
        assert "user=" in repr_str
