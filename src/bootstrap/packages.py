import subprocess
import logging
import shutil
from .environment import Environment, OS

logger = logging.getLogger(__name__)

class PackageManager:
    def __init__(self, env: Environment):
        self.env = env

    def install(self, package_name: str):
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
