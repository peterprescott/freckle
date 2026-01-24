import platform
import sys
import os
from enum import Enum
from pathlib import Path

class OS(Enum):
    LINUX = "linux"
    MACOS = "macos"
    UNKNOWN = "unknown"

class Environment:
    def __init__(self):
        self.os = self._detect_os()
        self.home = Path.home()
        self.user = os.environ.get("USER") or os.environ.get("LOGNAME") or self.home.name

    def _detect_os(self) -> OS:
        system = platform.system().lower()
        if system == "linux":
            return OS.LINUX
        elif system == "darwin":
            return OS.MACOS
        return OS.UNKNOWN

    def is_linux(self) -> bool:
        return self.os == OS.LINUX

    def is_macos(self) -> bool:
        return self.os == OS.MACOS

    def __repr__(self) -> str:
        return f"Environment(os={self.os.value}, home={self.home}, user={self.user})"
