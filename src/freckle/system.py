import logging
import os
import platform
import shutil
import subprocess
from enum import Enum
from pathlib import Path
from typing import Optional

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


class SystemPackageManager:
    """Platform-aware manager for installing system packages."""

    # Map distro IDs to package manager configurations
    DISTRO_PACKAGE_MANAGERS = {
        # Debian-based
        "debian": {
            "cmd": "apt",
            "install": ["apt", "install", "-y"],
            "update": ["apt", "update"],
        },
        "ubuntu": {
            "cmd": "apt",
            "install": ["apt", "install", "-y"],
            "update": ["apt", "update"],
        },
        "linuxmint": {
            "cmd": "apt",
            "install": ["apt", "install", "-y"],
            "update": ["apt", "update"],
        },
        "pop": {
            "cmd": "apt",
            "install": ["apt", "install", "-y"],
            "update": ["apt", "update"],
        },
        # Red Hat-based
        "fedora": {
            "cmd": "dnf",
            "install": ["dnf", "install", "-y"],
            "update": None,
        },
        "rhel": {
            "cmd": "dnf",
            "install": ["dnf", "install", "-y"],
            "update": None,
        },
        "centos": {
            "cmd": "dnf",
            "install": ["dnf", "install", "-y"],
            "update": None,
        },
        "rocky": {
            "cmd": "dnf",
            "install": ["dnf", "install", "-y"],
            "update": None,
        },
        "alma": {
            "cmd": "dnf",
            "install": ["dnf", "install", "-y"],
            "update": None,
        },
        # Arch-based
        "arch": {
            "cmd": "pacman",
            "install": ["pacman", "-S", "--noconfirm"],
            "update": ["pacman", "-Sy"],
        },
        "manjaro": {
            "cmd": "pacman",
            "install": ["pacman", "-S", "--noconfirm"],
            "update": ["pacman", "-Sy"],
        },
        "endeavouros": {
            "cmd": "pacman",
            "install": ["pacman", "-S", "--noconfirm"],
            "update": ["pacman", "-Sy"],
        },
        # SUSE-based
        "opensuse": {
            "cmd": "zypper",
            "install": ["zypper", "install", "-y"],
            "update": ["zypper", "refresh"],
        },
        "suse": {
            "cmd": "zypper",
            "install": ["zypper", "install", "-y"],
            "update": ["zypper", "refresh"],
        },
        # Alpine
        "alpine": {
            "cmd": "apk",
            "install": ["apk", "add"],
            "update": ["apk", "update"],
        },
    }

    def __init__(self, env: Environment):
        self.env = env
        self._is_root = os.geteuid() == 0 if hasattr(os, "geteuid") else False

    def _get_privilege_cmd(self) -> list:
        """Get the command prefix for privileged operations.

        Returns empty list if already root, ['sudo'] if sudo is available,
        or raises an error if privileges are needed but unavailable.
        """
        if self._is_root:
            return []

        if shutil.which("sudo"):
            return ["sudo"]

        # Check for doas (common on BSD, some Linux)
        if shutil.which("doas"):
            return ["doas"]

        logger.warning(
            "No privilege escalation tool found (sudo/doas). "
            "Package installation may fail if not running as root."
        )
        return []

    def _get_linux_package_manager(self) -> Optional[dict]:
        """Detect the appropriate package manager for this Linux distro."""
        distro = self.env.os_info.get("distro", "").lower()

        # Try exact match first
        if distro in self.DISTRO_PACKAGE_MANAGERS:
            return self.DISTRO_PACKAGE_MANAGERS[distro]

        # Try partial match (e.g., "opensuse-leap" matches "opensuse")
        for key, config in self.DISTRO_PACKAGE_MANAGERS.items():
            if key in distro or distro in key:
                return config

        # Fallback: detect by available package manager binary
        if shutil.which("apt"):
            return self.DISTRO_PACKAGE_MANAGERS["debian"]
        elif shutil.which("dnf"):
            return self.DISTRO_PACKAGE_MANAGERS["fedora"]
        elif shutil.which("yum"):
            return {
                "cmd": "yum",
                "install": ["yum", "install", "-y"],
                "update": None,
            }
        elif shutil.which("pacman"):
            return self.DISTRO_PACKAGE_MANAGERS["arch"]
        elif shutil.which("zypper"):
            return self.DISTRO_PACKAGE_MANAGERS["opensuse"]
        elif shutil.which("apk"):
            return self.DISTRO_PACKAGE_MANAGERS["alpine"]

        logger.error(f"Could not detect package manager for distro: {distro}")
        return None

    def install(self, package_name: str):
        """Install a package using the appropriate package manager."""
        if os.environ.get("FRECKLE_MOCK_PKGS"):
            logger.info(f"[MOCK] Installing {package_name}")
            return

        if self.env.is_macos():
            self._install_with_brew(package_name)
        elif self.env.is_linux():
            self._install_linux(package_name)
        else:
            logger.error(f"Cannot install {package_name}: Unsupported OS")

    def _install_linux(self, package_name: str):
        """Install a package on Linux using the detected package manager."""
        pkg_mgr = self._get_linux_package_manager()
        if not pkg_mgr:
            raise RuntimeError(
                "No supported package manager found for this system"
            )

        priv_cmd = self._get_privilege_cmd()

        # Run update if required by this package manager
        if pkg_mgr.get("update"):
            logger.info("Updating package lists...")
            update_cmd = priv_cmd + pkg_mgr["update"]
            subprocess.run(update_cmd, check=True)

        # Install the package
        logger.info(f"Installing {package_name} via {pkg_mgr['cmd']}...")
        install_cmd = priv_cmd + pkg_mgr["install"] + [package_name]
        subprocess.run(install_cmd, check=True)

    def _ensure_brew(self):
        """Install Homebrew if not present."""
        if shutil.which("brew"):
            return

        logger.info("Installing Homebrew...")
        # Must use shell=True because the command uses shell expansion $()
        install_script = (
            '/bin/bash -c "$(curl -fsSL '
            'https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
        )
        subprocess.run(install_script, shell=True, check=True)

    def _install_with_brew(self, package_name: str):
        """Install a package using Homebrew on macOS."""
        self._ensure_brew()
        logger.info(f"Installing {package_name} via Homebrew...")
        subprocess.run(["brew", "install", package_name], check=True)

    def is_installed(self, command_name: str) -> bool:
        """Check if a command is available in PATH."""
        return shutil.which(command_name) is not None

    def get_binary_info(self, command_name: str) -> dict:
        """Returns location and version of a binary."""
        path = shutil.which(command_name)
        if not path:
            return {"found": False}

        version = "unknown"
        try:
            if command_name == "tmux":
                cmd = [path, "-V"]
            else:
                cmd = [path, "--version"]

            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=2
            )
            if result.returncode == 0:
                # Most tools output 'toolname v1.2.3' on the first line
                version = result.stdout.splitlines()[0].strip()
        except Exception:
            pass

        return {"found": True, "path": path, "version": version}
