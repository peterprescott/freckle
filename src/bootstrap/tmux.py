import logging
from .environment import Environment
from .packages import PackageManager

logger = logging.getLogger(__name__)

class TmuxManager:
    def __init__(self, env: Environment, pkg_mgr: PackageManager):
        self.env = env
        self.pkg_mgr = pkg_mgr

    def setup(self):
        logger.info("Setting up Tmux...")
        
        if not self.pkg_mgr.is_installed("tmux"):
            self.pkg_mgr.install("tmux")
