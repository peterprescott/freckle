from __future__ import annotations

import copy
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, cast

import yaml

if TYPE_CHECKING:
    from .system import Environment


class Config:
    """Configuration manager for freckle."""

    DEFAULT_CONFIG: Dict[str, Any] = {
        "vars": {},
        "dotfiles": {"repo_url": None, "dir": "~/.dotfiles"},
        "profiles": {},
        "tools": {},
        "secrets": {
            "block": [],
            "allow": [],
        },
    }

    def __init__(
        self,
        config_path: Optional[Path] = None,
        env: Optional[Environment] = None,
    ):
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

    def _deep_update(self, base: Dict, update: Dict) -> None:
        for k, v in update.items():
            if isinstance(v, dict) and k in base and isinstance(base[k], dict):
                self._deep_update(base[k], v)
            else:
                base[k] = v

    def _apply_replacements(self, data: Any) -> None:
        """Replace {local_user} and custom vars in the config data."""
        replacements = {"local_user": self.env.user if self.env else "user"}
        if "vars" in self.data and isinstance(self.data["vars"], dict):
            replacements.update(self.data["vars"])
        self._walk_and_format(data, replacements)

    def _walk_and_format(
        self, data: Any, replacements: Dict[str, str]
    ) -> None:
        if isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, (dict, list)):
                    self._walk_and_format(v, replacements)
                elif isinstance(v, str):
                    try:
                        data[k] = v.format(**replacements)
                    except KeyError:
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
        """Get a config value by dot-separated path."""
        keys = key_path.split(".")
        value = self.data
        try:
            for key in keys:
                value = value[key]
            return value
        except (KeyError, TypeError):
            return default

    def get_profiles(self) -> Dict[str, Dict[str, Any]]:
        """Get all profile definitions."""
        profiles = self.data.get("profiles", {})
        return cast(Dict[str, Dict[str, Any]], profiles)

    def get_profile(self, name: str) -> Optional[Dict[str, Any]]:
        """Get a specific profile by name."""
        profiles = self.get_profiles()
        return profiles.get(name)

    def get_profile_branch(self, profile_name: str) -> str:
        """Get the branch for a profile (same as profile name)."""
        return profile_name

    def get_profile_modules(self, profile_name: str) -> List[str]:
        """Get the modules for a profile."""
        profile = self.get_profile(profile_name)
        if profile:
            return profile.get("modules", [])
        return []

    def list_profile_names(self) -> List[str]:
        """Get list of all profile names."""
        return list(self.get_profiles().keys())

    def get_branch(self) -> str:
        """Get the current branch from the first profile."""
        profiles = self.get_profiles()
        if profiles:
            first_profile = list(profiles.keys())[0]
            return self.get_profile_branch(first_profile)
        return "main"

    def get_modules(self) -> List[str]:
        """Get the modules from the first profile."""
        profiles = self.get_profiles()
        if profiles:
            first_profile = list(profiles.keys())[0]
            return self.get_profile_modules(first_profile)
        return []
