"""Freckle - Keep track of all your dot(file)s."""

from .cli import main
from .config import Config
from .dotfiles import DotfilesManager
from .system import Environment
from .utils import get_version

__all__ = [
    "Config",
    "DotfilesManager",
    "Environment",
    "get_version",
    "main",
]
