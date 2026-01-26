import os
import shutil
import subprocess

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
        """Set Zsh as default shell if not already."""
        current_shell = os.environ.get("SHELL", "")
        if "zsh" in current_shell:
            self.logger.debug("Zsh is already the default shell")
            return

        if os.environ.get("FRECKLE_MOCK_PKGS"):
            self.logger.info("[MOCK] Setting Zsh as default shell...")
            return

        zsh_path = shutil.which("zsh")
        if not zsh_path:
            self.logger.error("Zsh binary not found in PATH after installation")
            return

        # Check if zsh is in /etc/shells (required for chsh)
        try:
            with open("/etc/shells", "r") as f:
                valid_shells = f.read().splitlines()
            if zsh_path not in valid_shells:
                self.logger.warning(
                    f"Zsh ({zsh_path}) is not in /etc/shells. "
                    "You may need to add it manually before changing shells."
                )
        except FileNotFoundError:
            pass  # /etc/shells doesn't exist on all systems

        # Try different methods to change shell
        if self._try_usermod(zsh_path):
            return
        if self._try_chsh(zsh_path):
            return

        self.logger.warning(
            f"Could not automatically set Zsh as default shell. "
            f"Please run manually: chsh -s {zsh_path}"
        )

    def _try_usermod(self, zsh_path: str) -> bool:
        """Try to change shell using usermod (requires root/sudo)."""
        # usermod doesn't prompt for password when using sudo
        if not shutil.which("usermod"):
            return False

        try:
            # Check if we're root or have passwordless sudo
            priv_cmd = []
            if os.geteuid() != 0:
                if not shutil.which("sudo"):
                    return False
                priv_cmd = ["sudo", "-n"]  # -n = non-interactive

            self.logger.info("Setting Zsh as default shell using usermod...")
            cmd = priv_cmd + ["usermod", "-s", zsh_path, self.env.user]
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                self.logger.info("Successfully set Zsh as default shell")
                return True
            else:
                self.logger.debug(f"usermod failed: {result.stderr}")
                return False
        except Exception as e:
            self.logger.debug(f"usermod failed: {e}")
            return False

    def _try_chsh(self, zsh_path: str) -> bool:
        """Try to change shell using chsh.

        Note: chsh often prompts for password even with sudo, so we try
        non-interactively first and fall back to informing the user.
        """
        if not shutil.which("chsh"):
            return False

        try:
            # Try chsh without sudo first (works on some systems)
            self.logger.info("Attempting to set Zsh as default shell...")

            # Use -s flag with the shell path
            result = subprocess.run(
                ["chsh", "-s", zsh_path],
                capture_output=True,
                text=True,
                timeout=5  # Don't hang if it prompts for password
            )

            if result.returncode == 0:
                self.logger.info("Successfully set Zsh as default shell")
                return True

            self.logger.debug(f"chsh failed: {result.stderr}")
            return False

        except subprocess.TimeoutExpired:
            self.logger.debug("chsh timed out (likely waiting for password)")
            return False
        except Exception as e:
            self.logger.debug(f"chsh failed: {e}")
            return False
