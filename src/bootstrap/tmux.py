import logging
from .environment import Environment
from .packages import PackageManager

logger = logging.getLogger(__name__)

class TmuxManager:
    def __init__(self, env: Environment, pkg_mgr: PackageManager):
        self.env = env
        self.pkg_mgr = pkg_mgr

    def setup(self):
        logger.info("Verifying Tmux installation...")
        
        if not self.pkg_mgr.is_installed("tmux"):
            logger.info("Tmux not found. Installing...")
            self.pkg_mgr.install("tmux")
