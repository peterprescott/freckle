import subprocess
from .base import BaseToolManager

class NvimManager(BaseToolManager):
    @property
    def name(self) -> str:
        return "Neovim"

    @property
    def bin_name(self) -> str:
        return "nvim"

    @property
    def package_name(self) -> str:
        return "neovim"

    @property
    def config_files(self) -> list:
        return [".config/nvim/init.lua", ".config/nvim/init.vim"]

    def _post_install(self):
        config_dir = self.env.home / ".config" / "nvim"
        config_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_lazy_nvim()

    def _ensure_lazy_nvim(self):
        """Installs lazy.nvim if it's missing."""
        lazy_path = self.env.home / ".local" / "share" / "nvim" / "lazy" / "lazy.nvim"
        if not lazy_path.exists():
            self.logger.info("Installing lazy.nvim...")
            subprocess.run([
                "git", "clone", "--filter=blob:none",
                "https://github.com/folke/lazy.nvim.git",
                "--branch=stable",
                str(lazy_path)
            ], check=True)
        else:
            self.logger.debug("lazy.nvim already installed.")
