"""Bootstrap - A robust, multi-platform system bootstrapper for Linux and macOS."""

from .cli import BootstrapCLI, main
from .config import Config
from .dotfiles import DotfilesManager
from .environment import Environment
from .packages import PackageManager
from .utils import get_version

__all__ = [
    "BootstrapCLI",
    "Config",
    "DotfilesManager",
    "Environment",
    "PackageManager",
    "get_version",
    "main",
]
