import subprocess
import logging
from pathlib import Path
from .environment import Environment
from .packages import PackageManager

logger = logging.getLogger(__name__)

class NvimManager:
    def __init__(self, env: Environment, pkg_mgr: PackageManager):
        self.env = env
        self.pkg_mgr = pkg_mgr
        self.config_dir = env.home / ".config" / "nvim"
        self.init_lua = self.config_dir / "init.lua"
        self.init_vim = self.config_dir / "init.vim"

    def setup(self):
        """Ensures Neovim is installed and configured."""
        logger.info("Setting up Neovim...")
        
        # 0. Ensure neovim is installed
        if not self.pkg_mgr.is_installed("nvim"):
            self.pkg_mgr.install("neovim")

        # 1. Ensure config directory exists
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        # 2. Check for lazy.nvim
        self._ensure_lazy_nvim()
        
        # 3. Handle init.vim -> init.lua migration
        if self.init_vim.exists() and not self.init_lua.exists():
            logger.info("Found existing init.vim but no init.lua. Migration recommended.")
            # In a real scenario, we might auto-migrate or just warn.
            # For now, we'll let the user decide.

    def _ensure_lazy_nvim(self):
        """Installs lazy.nvim if it's missing."""
        lazy_path = self.env.home / ".local" / "share" / "nvim" / "lazy" / "lazy.nvim"
        if not lazy_path.exists():
            logger.info("Installing lazy.nvim...")
            subprocess.run([
                "git", "clone", "--filter=blob:none",
                "https://github.com/folke/lazy.nvim.git",
                "--branch=stable",
                str(lazy_path)
            ], check=True)
        else:
            logger.debug("lazy.nvim already installed.")
