import subprocess
import logging
import shutil
import os
from .environment import Environment, OS

logger = logging.getLogger(__name__)

class PackageManager:
    def __init__(self, env: Environment):
        self.env = env

    def install(self, package_name: str):
        if os.environ.get("BOOTSTRAP_MOCK_PKGS"):
            logger.info(f"[MOCK] Installing {package_name}")
            return

        if self.env.is_macos():
            self._install_with_brew(package_name)
        elif self.env.is_linux():
            self._install_with_apt(package_name)
        else:
            logger.error(f"Cannot install {package_name}: Unsupported OS")

    def _ensure_brew(self):
        if not shutil.which("brew"):
            logger.info("Installing Homebrew...")
            subprocess.run(
                ["/bin/bash", "-c", "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"],
                check=True
            )

    def _install_with_brew(self, package_name: str):
        self._ensure_brew()
        logger.info(f"Installing {package_name} via Homebrew...")
        subprocess.run(["brew", "install", package_name], check=True)

    def _install_with_apt(self, package_name: str):
        # We could check if apt is available, but for now we assume it is on Linux/Debian
        logger.info(f"Installing {package_name} via apt...")
        # Note: This might require sudo
        subprocess.run(["sudo", "apt", "update"], check=True)
        subprocess.run(["sudo", "apt", "install", "-y", package_name], check=True)

    def is_installed(self, command_name: str) -> bool:
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
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
            if result.returncode == 0:
                # Most tools output 'toolname v1.2.3' on the first line
                version = result.stdout.splitlines()[0].strip()
        except Exception:
            pass

        return {
            "found": True,
            "path": path,
            "version": version
        }
