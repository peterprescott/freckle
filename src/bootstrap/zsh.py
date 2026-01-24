import subprocess
import os
from .base import BaseToolManager

class ZshManager(BaseToolManager):
    @property
    def name(self) -> str:
        return "Zsh"

    @property
    def bin_name(self) -> str:
        return "zsh"

    @property
    def config_files(self) -> list:
        return [".zshrc"]

    def _post_install(self):
        current_shell = os.environ.get("SHELL", "")
        if "zsh" not in current_shell:
            if os.environ.get("BOOTSTRAP_MOCK_PKGS"):
                self.logger.info("[MOCK] Setting Zsh as default shell...")
                return
            self.logger.info("Setting Zsh as default shell...")
            zsh_path = subprocess.check_output(["which", "zsh"]).decode().strip()
            subprocess.run(["sudo", "chsh", "-s", zsh_path, self.env.user], check=True)
