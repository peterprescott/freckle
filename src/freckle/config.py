from __future__ import annotations

import copy
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, cast

import yaml

if TYPE_CHECKING:
    from .system import Environment


class Config:
    """Configuration manager for freckle.

    Supports both v1 (legacy) and v2 (profiles) config formats.
    V1 configs are auto-migrated to v2 on load.
    """

    DEFAULT_CONFIG = {
        "version": 2,
        "vars": {},
        "dotfiles": {"repo_url": None, "dir": "~/.dotfiles"},
        "profiles": {},
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
        self._migrated = False

        if config_path and config_path.exists():
            with open(config_path, "r") as f:
                user_config = yaml.safe_load(f)
                if user_config:
                    # Check if migration needed
                    if self._needs_migration(user_config):
                        user_config = self._migrate_v1_to_v2(user_config)
                        self._migrated = True

                    self._deep_update(self.data, user_config)

        if self.env:
            self._apply_replacements(self.data)

    @property
    def migrated(self) -> bool:
        """True if config was migrated from v1 format."""
        return self._migrated

    def _needs_migration(self, config: Dict) -> bool:
        """Check if config is v1 format and needs migration."""
        # V1 has 'modules' list and no 'version' or 'profiles'
        has_modules = "modules" in config and isinstance(
            config["modules"], list
        )
        has_version = "version" in config
        has_profiles = "profiles" in config

        return has_modules and not has_version and not has_profiles

    def _migrate_v1_to_v2(self, config: Dict) -> Dict:
        """Migrate v1 config to v2 format.

        V1 format:
            dotfiles:
              branch: main
              dir: .dotfiles
              repo_url: https://...
            modules:
              - dotfiles
              - zsh
              - nvim

        V2 format:
            version: 2
            dotfiles:
              dir: .dotfiles
              repo_url: https://...
            profiles:
              main:
                description: "Migrated from v1"
                modules: [zsh, nvim]
        """
        # Extract branch (default to main)
        branch = config.get("dotfiles", {}).get("branch", "main")

        # Extract modules, removing 'dotfiles' (now implicit)
        modules = [
            m for m in config.get("modules", []) if m != "dotfiles"
        ]

        # Build v2 config
        v2_config = {
            "version": 2,
            "vars": config.get("vars", {}),
            "dotfiles": {
                "dir": config.get("dotfiles", {}).get("dir", "~/.dotfiles"),
                "repo_url": config.get("dotfiles", {}).get("repo_url"),
            },
            "profiles": {
                branch: {
                    "description": "Migrated from v1 config",
                    "modules": modules,
                }
            },
            "secrets": config.get("secrets", {"block": [], "allow": []}),
        }

        return v2_config

    def _deep_update(self, base: Dict, update: Dict):
        for k, v in update.items():
            if isinstance(v, dict) and k in base and isinstance(base[k], dict):
                self._deep_update(base[k], v)
            else:
                base[k] = v

    def _apply_replacements(self, data: Any):
        """Replace {local_user} and custom vars in the config data."""
        replacements = {"local_user": self.env.user if self.env else "user"}
        if "vars" in self.data and isinstance(self.data["vars"], dict):
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
        """Get the branch for a profile (defaults to profile name)."""
        profile = self.get_profile(profile_name)
        if profile:
            return profile.get("branch", profile_name)
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

    # Backward compatibility: get branch from first profile or legacy location
    def get_branch(self) -> str:
        """Get the current branch (for backward compatibility)."""
        # First try profiles
        profiles = self.get_profiles()
        if profiles:
            # Return first profile's branch
            first_profile = list(profiles.keys())[0]
            return self.get_profile_branch(first_profile)

        # Fall back to legacy dotfiles.branch
        dotfiles_data = self.data.get("dotfiles", {})
        if isinstance(dotfiles_data, dict):
            branch = dotfiles_data.get("branch", "main")
            if isinstance(branch, str):
                return branch
        return "main"

    # Backward compatibility: get modules from first profile or legacy location
    def get_modules(self) -> List[str]:
        """Get the current modules (for backward compatibility)."""
        # First try profiles
        profiles = self.get_profiles()
        if profiles:
            first_profile = list(profiles.keys())[0]
            return self.get_profile_modules(first_profile)

        # Fall back to legacy modules list, filtering out 'dotfiles'
        modules = self.data.get("modules", [])
        if isinstance(modules, list):
            return [
                m for m in modules
                if isinstance(m, str) and m != "dotfiles"
            ]
        return []
