from __future__ import annotations

import copy
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple, cast

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
        """Get resolved modules for a profile (including inherited).

        Returns a sorted list for consistent ordering.
        """
        try:
            modules, _ = self.resolve_profile_modules(profile_name)
            return sorted(modules)
        except ValueError:
            # Fallback for invalid configs - return direct modules only
            profile = self.get_profile(profile_name)
            return sorted(profile.get("modules", [])) if profile else []

    def resolve_profile_modules(
        self,
        profile_name: str,
        _visited: Optional[Set[str]] = None,
    ) -> Tuple[Set[str], List[str]]:
        """Resolve all modules for a profile, including inherited ones.

        Uses set operations:
        1. Union all inherited modules from included profiles
        2. Subtract any excluded modules
        3. Union own modules

        Args:
            profile_name: The profile to resolve
            _visited: Internal set for cycle detection

        Returns:
            Tuple of (resolved modules set, list of warnings)

        Raises:
            ValueError: If circular dependency or self-reference detected
        """
        if _visited is None:
            _visited = set()

        warnings: List[str] = []

        # Check for circular dependency
        if profile_name in _visited:
            cycle = " -> ".join(list(_visited) + [profile_name])
            raise ValueError(f"Circular profile dependency: {cycle}")

        profile = self.get_profile(profile_name)
        if profile is None:
            raise ValueError(f"Unknown profile: {profile_name}")

        _visited = _visited | {profile_name}

        # Step 1: Collect inherited modules from all includes
        inherited: Set[str] = set()
        for include_name in profile.get("include", []):
            if include_name == profile_name:
                raise ValueError(
                    f"Profile '{profile_name}' cannot include itself"
                )

            if include_name not in self.get_profiles():
                warnings.append(
                    f"Profile '{profile_name}' includes unknown profile "
                    f"'{include_name}' (skipped)"
                )
                continue

            included_modules, sub_warnings = self.resolve_profile_modules(
                include_name, _visited.copy()
            )
            inherited |= included_modules
            warnings.extend(sub_warnings)

        # Step 2: Remove excluded modules
        excluded: Set[str] = set(profile.get("exclude", []))
        inherited -= excluded

        # Step 3: Add own modules
        own_modules: Set[str] = set(profile.get("modules", []))
        resolved = inherited | own_modules

        return resolved, warnings

    def validate_profile_includes(self) -> Tuple[List[str], List[str]]:
        """Validate all profile include references.

        Returns:
            Tuple of (errors, warnings)
            - errors: Fatal issues (circular deps, self-reference)
            - warnings: Non-fatal issues (missing includes, deep inheritance)
        """
        errors: List[str] = []
        warnings: List[str] = []
        profiles = self.get_profiles()

        for name, profile in profiles.items():
            includes = profile.get("include", [])

            # Check for self-include (error)
            if name in includes:
                errors.append(f"Profile '{name}' cannot include itself")
                continue

            # Check for missing includes (warning)
            for include_name in includes:
                if include_name not in profiles:
                    warnings.append(
                        f"Profile '{name}' includes unknown profile "
                        f"'{include_name}'"
                    )

            # Check for cycles (error)
            try:
                _, resolution_warnings = self.resolve_profile_modules(name)
                warnings.extend(resolution_warnings)
            except ValueError as e:
                errors.append(str(e))

            # Check for deep inheritance (warning)
            depth = self.get_profile_inheritance_depth(name)
            if depth > 3:
                warnings.append(
                    f"Profile '{name}' has deep inheritance ({depth} levels)"
                )

        return errors, warnings

    def get_profile_inheritance_depth(
        self,
        profile_name: str,
        _visited: Optional[Set[str]] = None,
    ) -> int:
        """Get the maximum inheritance depth for a profile.

        Returns 0 for profiles with no includes.
        Returns 0 if circular dependency detected (avoids recursion).
        """
        if _visited is None:
            _visited = set()

        # Avoid infinite recursion on circular deps
        if profile_name in _visited:
            return 0

        profile = self.get_profile(profile_name)
        if not profile:
            return 0

        includes = profile.get("include", [])
        if not includes:
            return 0

        _visited = _visited | {profile_name}

        max_depth = 0
        for include_name in includes:
            if include_name in self.get_profiles():
                depth = self.get_profile_inheritance_depth(
                    include_name, _visited
                )
                max_depth = max(max_depth, depth)

        return max_depth + 1

    def list_profile_names(self) -> List[str]:
        """Get list of all profile names."""
        return list(self.get_profiles().keys())

    def get_default_branch(self) -> str:
        """Get the default branch name from the first profile.

        Note: This returns the configured default, not the actual git branch.
        Use get_dotfiles_manager() to get a manager with the actual branch.
        """
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
