import subprocess
import logging
import os
from .environment import Environment
from .packages import PackageManager

logger = logging.getLogger(__name__)

class ZshManager:
    def __init__(self, env: Environment, pkg_mgr: PackageManager):
        self.env = env
        self.pkg_mgr = pkg_mgr

    def setup(self):
        logger.info("Setting up Zsh...")
        
        if not self.pkg_mgr.is_installed("zsh"):
            self.pkg_mgr.install("zsh")

        current_shell = os.environ.get("SHELL", "")
        if "zsh" not in current_shell:
            if os.environ.get("BOOTSTRAP_MOCK_PKGS"):
                logger.info("[MOCK] Setting Zsh as default shell...")
                return
            logger.info("Setting Zsh as default shell...")
            zsh_path = subprocess.check_output(["which", "zsh"]).decode().strip()
            subprocess.run(["sudo", "chsh", "-s", zsh_path, self.env.user], check=True)
