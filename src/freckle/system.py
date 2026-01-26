import logging
import os
import platform
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class OS(Enum):
    LINUX = "linux"
    MACOS = "macos"
    UNKNOWN = "unknown"


class Environment:
    """Detects and provides info about the current system environment."""

    def __init__(self):
        self.os = self._detect_os()
        self.home = Path.home()
        self.user = (
            os.environ.get("USER")
            or os.environ.get("LOGNAME")
            or self.home.name
        )
        self.os_info = self._get_os_info()

    def _detect_os(self) -> OS:
        system = platform.system().lower()
        if system == "linux":
            return OS.LINUX
        elif system == "darwin":
            return OS.MACOS
        return OS.UNKNOWN

    def _get_os_info(self) -> dict:
        info = {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "pretty_name": platform.system(),
        }

        if self.is_linux():
            # Try to get distro info from /etc/os-release
            os_release = Path("/etc/os-release")
            if os_release.exists():
                data = {}
                with open(os_release) as f:
                    for line in f:
                        if "=" in line:
                            k, v = line.rstrip().split("=", 1)
                            data[k] = v.strip('"')
                info["pretty_name"] = data.get("PRETTY_NAME", "Linux")
                info["distro"] = data.get("ID", "linux")
                info["distro_version"] = data.get("VERSION_ID", "")
        elif self.is_macos():
            info["pretty_name"] = f"macOS {platform.mac_ver()[0]}"
            info["distro"] = "macos"
            info["distro_version"] = platform.mac_ver()[0]

        return info

    def is_linux(self) -> bool:
        return self.os == OS.LINUX

    def is_macos(self) -> bool:
        return self.os == OS.MACOS

    def __repr__(self) -> str:
        return (
            f"Environment(os={self.os.value}, "
            f"home={self.home}, user={self.user})"
        )
