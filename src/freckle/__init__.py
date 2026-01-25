"""Freckle - Keep track of all your dot(file)s."""

from .cli import FreckleCLI, main
from .config import Config
from .dotfiles import DotfilesManager
from .environment import Environment
from .system import SystemPackageManager
from .utils import get_version

__all__ = [
    "FreckleCLI",
    "Config",
    "DotfilesManager",
    "Environment",
    "SystemPackageManager",
    "get_version",
    "main",
]
