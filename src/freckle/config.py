from __future__ import annotations
import copy
import yaml
from pathlib import Path
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .environment import Environment

class Config:
    DEFAULT_CONFIG = {
        "vars": {},
        "dotfiles": {
            "repo_url": None,
            "branch": "main",
            "dir": "~/.dotfiles"
        },
        "modules": ["dotfiles", "zsh", "tmux", "nvim"]
    }

    def __init__(self, config_path: Optional[Path] = None, env: Optional[Environment] = None):
        # Use deepcopy to avoid mutating the class-level DEFAULT_CONFIG
        self.data = copy.deepcopy(self.DEFAULT_CONFIG)
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
        """Recursively replaces {local_user} and custom vars in the config data."""
        # Build the dictionary of available replacements
        replacements = {
            "local_user": self.env.user if self.env else "user"
        }
        # Merge in custom vars from the config itself
        if "vars" in self.data:
            replacements.update(self.data["vars"])

        self._walk_and_format(data, replacements)

    def _walk_and_format(self, data: Any, replacements: Dict[str, str]):
        if isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, (dict, list)):
                    self._walk_and_format(v, replacements)
                elif isinstance(v, str):
                    try:
                        data[k] = v.format(**replacements)
                    except KeyError as e:
                        # If a tag is missing, we just leave it alone
                        pass
        elif isinstance(data, list):
            for i, v in enumerate(data):
                if isinstance(v, (dict, list)):
                    self._walk_and_format(v, replacements)
                elif isinstance(v, str):
                    try:
                        data[i] = v.format(**replacements)
                    except KeyError:
                        pass

    def get(self, key_path: str, default: Any = None) -> Any:
        keys = key_path.split(".")
        value = self.data
        try:
            for key in keys:
                value = value[key]
            return value
        except (KeyError, TypeError):
            return default
