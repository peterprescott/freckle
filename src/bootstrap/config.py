import yaml
from pathlib import Path
from typing import Any, Dict, Optional

class Config:
    DEFAULT_CONFIG = {
        "dotfiles": {
            "repo_url": "https://github.com/peterprescott/.dotfiles.git",
            "branch": "master",
            "dir": "~/.dotfiles"
        }
    }

    def __init__(self, config_path: Optional[Path] = None):
        self.data = self.DEFAULT_CONFIG.copy()
        if config_path and config_path.exists():
            with open(config_path, "r") as f:
                user_config = yaml.safe_load(f)
                if user_config:
                    self._deep_update(self.data, user_config)

    def _deep_update(self, base: Dict, update: Dict):
        for k, v in update.items():
            if isinstance(v, dict) and k in base and isinstance(base[k], dict):
                self._deep_update(base[k], v)
            else:
                base[k] = v

    def get(self, key_path: str, default: Any = None) -> Any:
        keys = key_path.split(".")
        value = self.data
        try:
            for key in keys:
                value = value[key]
            return value
        except (KeyError, TypeError):
            return default
