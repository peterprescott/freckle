import logging
from abc import ABC, abstractmethod
from typing import List

from ..system import Environment, SystemPackageManager


class BaseToolManager(ABC):
    def __init__(self, env: Environment, pkg_mgr: SystemPackageManager):
        self.env = env
        self.pkg_mgr = pkg_mgr
        self.logger = logging.getLogger(self.__class__.__module__)

    @property
    @abstractmethod
    def name(self) -> str:
        """The display name of the tool."""
        pass

    @property
    @abstractmethod
    def bin_name(self) -> str:
        """The binary name to check for installation."""
        pass

    @property
    def package_name(self) -> str:
        """The package name to install if different from bin_name."""
        return self.bin_name

    @property
    def config_files(self) -> List[str]:
        """List of configuration files relative to HOME."""
        return []

    def setup(self):
        self.logger.info(f"Verifying {self.name} installation...")

        if not self.pkg_mgr.is_installed(self.bin_name):
            self.logger.info(f"{self.name} not found. Installing...")
            self.pkg_mgr.install(self.package_name)

        self._post_install()

    def _post_install(self):
        """Hook for tool-specific configuration after ensuring it's installed."""
        pass
