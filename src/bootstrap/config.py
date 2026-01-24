from __future__ import annotations
import yaml
from pathlib import Path
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .environment import Environment

class Config:
    DEFAULT_CONFIG = {
        "dotfiles": {
            "repo_url": None,
            "branch": "master",
            "dir": "~/.dotfiles"
        },
        "modules": ["dotfiles", "zsh", "tmux", "nvim"]
    }

    def __init__(self, config_path: Optional[Path] = None, env: Optional[Environment] = None):
        self.data = self.DEFAULT_CONFIG.copy()
        self.env = env
        if config_path and config_path.exists():
            with open(config_path, "r") as f:
                user_config = yaml.safe_load(f)
                if user_config:
                    self._deep_update(self.data, user_config)
        
        if self.env:
            self._apply_replacements(self.data)

    def _deep_update(self, base: Dict, update: Dict):
        for k, v in update.items():
            if isinstance(v, dict) and k in base and isinstance(base[k], dict):
                self._deep_update(base[k], v)
            else:
                base[k] = v

    def _apply_replacements(self, data: Any):
        """Recursively replaces {username} etc in the config data."""
        if isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, (dict, list)):
                    self._apply_replacements(v)
                elif isinstance(v, str):
                    data[k] = v.format(username=self.env.user)
        elif isinstance(data, list):
            for i, v in enumerate(data):
                if isinstance(v, (dict, list)):
                    self._apply_replacements(v)
                elif isinstance(v, str):
                    data[i] = v.format(username=self.env.user)

    def get(self, key_path: str, default: Any = None) -> Any:
        keys = key_path.split(".")
        value = self.data
        try:
            for key in keys:
                value = value[key]
            return value
        except (KeyError, TypeError):
            return default
