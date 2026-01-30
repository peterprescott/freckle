"""Declarative tool definitions and registry for freckle.

This module provides:
- Tool schema for declarative tool definitions
- Curated script registry for safe installations
- Package manager abstraction
- Tool installation and verification
"""

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# Curated install scripts - known-good URLs for tools that need curl|sh
# These are pinned to specific versions or known-stable endpoints
CURATED_SCRIPTS: Dict[str, str] = {
    "uv": "https://astral.sh/uv/install.sh",
    "rustup": "https://sh.rustup.rs",
    "starship": "https://starship.rs/install.sh",
    "nvm": (
        "https://raw.githubusercontent.com/nvm-sh/nvm/"
        "v0.40.1/install.sh"
    ),
    "rye": "https://rye.astral.sh/get",
    "mise": "https://mise.run",
    "atuin": "https://setup.atuin.sh",
    "ghcup": "https://get-ghcup.haskell.org",
    "sdkman": "https://get.sdkman.io",
    "homebrew": (
        "https://raw.githubusercontent.com/Homebrew/install/"
        "HEAD/install.sh"
    ),
    "bun": "https://bun.sh/install",
    "deno": "https://deno.land/install.sh",
    "gh": (
        "https://raw.githubusercontent.com/max-programming/"
        "gh-cli-installer/main/debian.sh"
    ),
}


# Package manager detection and commands
@dataclass
class PackageManager:
    """Abstraction for a package manager."""

    name: str
    check_cmd: List[str]
    install_cmd: List[str]
    sudo_required: bool = False

    def is_available(self) -> bool:
        """Check if this package manager is available."""
        try:
            subprocess.run(
                self.check_cmd,
                check=True,
                capture_output=True,
                timeout=10,
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError, OSError):
            return False

    def install(self, package: str) -> bool:
        """Install a package. Returns True on success."""
        cmd = self.install_cmd + [package]
        if self.sudo_required:
            cmd = ["sudo"] + cmd

        try:
            subprocess.run(cmd, check=True, timeout=300)
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to install {package} via {self.name}: {e}")
            return False


# Supported package managers
PACKAGE_MANAGERS: Dict[str, PackageManager] = {
    "brew": PackageManager(
        name="brew",
        check_cmd=["brew", "--version"],
        install_cmd=["brew", "install"],
    ),
    "brew_cask": PackageManager(
        name="brew_cask",
        check_cmd=["brew", "--version"],
        install_cmd=["brew", "install", "--cask"],
    ),
    "apt": PackageManager(
        name="apt",
        check_cmd=["apt", "--version"],
        install_cmd=["apt", "install", "-y"],
        sudo_required=True,
    ),
    "cargo": PackageManager(
        name="cargo",
        check_cmd=["cargo", "--version"],
        install_cmd=["cargo", "install"],
    ),
    "pip": PackageManager(
        name="pip",
        check_cmd=["pip", "--version"],
        install_cmd=["pip", "install"],
    ),
    "uv_tool": PackageManager(
        name="uv_tool",
        check_cmd=["uv", "--version"],
        install_cmd=["uv", "tool", "install"],
    ),
    "mise": PackageManager(
        name="mise",
        check_cmd=["mise", "--version"],
        install_cmd=["mise", "use", "-g"],
    ),
    "npm": PackageManager(
        name="npm",
        check_cmd=["npm", "--version"],
        install_cmd=["npm", "install", "-g"],
    ),
}


@dataclass
class ToolDefinition:
    """Definition of a tool that can be installed."""

    name: str
    description: str = ""
    install: Dict[str, str] = field(default_factory=dict)
    verify: Optional[str] = None
    config_files: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, name: str, data: Dict[str, Any]) -> "ToolDefinition":
        """Create a ToolDefinition from config dict."""
        install = data.get("install", {})
        if isinstance(install, str):
            # Simple form: just a package name
            install = {"brew": install, "apt": install}

        return cls(
            name=name,
            description=data.get("description", ""),
            install=install,
            verify=data.get("verify"),
            config_files=data.get("config", []),
        )

    def is_installed(self) -> bool:
        """Check if this tool is installed."""
        if self.verify:
            # Use explicit verify command with shell=True to handle
            # quotes, pipes, and other shell constructs
            try:
                subprocess.run(
                    self.verify,
                    shell=True,
                    check=True,
                    capture_output=True,
                    timeout=10,
                )
                return True
            except (
                subprocess.CalledProcessError,
                FileNotFoundError,
                OSError,
                subprocess.TimeoutExpired,
            ):
                return False

        # Fallback: check if tool name is in PATH
        return shutil.which(self.name) is not None

    def get_version(self) -> Optional[str]:
        """Try to get the installed version."""
        # Common version flags
        for flag in ["--version", "-V", "version"]:
            try:
                result = subprocess.run(
                    [self.name, flag],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode == 0:
                    # Extract first line, often contains version
                    first_line = result.stdout.strip().split("\n")[0]
                    return first_line
            except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
                continue
        return None


class ToolsRegistry:
    """Registry and installer for configured tools."""

    def __init__(self, tools_config: Dict[str, Dict[str, Any]]):
        """Initialize with tools config section."""
        self.tools: Dict[str, ToolDefinition] = {}
        for name, data in tools_config.items():
            self.tools[name] = ToolDefinition.from_dict(name, data)

    def list_tools(self) -> List[ToolDefinition]:
        """Get all configured tools."""
        return list(self.tools.values())

    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        """Get a specific tool by name."""
        return self.tools.get(name)

    def get_available_managers(self) -> List[str]:
        """Get list of available package managers."""
        return [
            name for name, pm in PACKAGE_MANAGERS.items()
            if pm.is_available()
        ]

    def install_tool(
        self,
        tool: ToolDefinition,
        confirm_script: bool = True,
    ) -> bool:
        """Install a tool using available package managers.

        Tries package managers in order of preference, falling back
        to curated script if available.

        Args:
            tool: The tool to install
            confirm_script: If True, require confirmation for scripts

        Returns:
            True if installation succeeded
        """
        # Order of preference for package managers
        manager_order = [
            "brew", "brew_cask", "apt", "cargo",
            "uv_tool", "mise", "pip", "npm",
        ]

        # Try each configured package manager
        for pm_name in manager_order:
            if pm_name not in tool.install:
                continue

            pm = PACKAGE_MANAGERS.get(pm_name)
            if not pm or not pm.is_available():
                continue

            package = tool.install[pm_name]
            logger.info(f"Installing {tool.name} via {pm_name}...")

            if pm.install(package):
                return True

        # Try curated script
        if "script" in tool.install:
            script_key = tool.install["script"]
            script_url = CURATED_SCRIPTS.get(script_key)

            if script_url:
                return self._install_via_script(
                    tool.name,
                    script_url,
                    confirm=confirm_script,
                )
            else:
                logger.warning(
                    f"Script '{script_key}' not in curated registry"
                )

        logger.error(f"No available install method for {tool.name}")
        return False

    def _install_via_script(
        self,
        name: str,
        url: str,
        confirm: bool = True,
    ) -> bool:
        """Install a tool via curated script.

        Args:
            name: Tool name
            url: Curated script URL
            confirm: Whether to prompt for confirmation

        Returns:
            True if installation succeeded
        """
        logger.info(f"Installing {name} via curated script...")
        logger.info(f"  Source: {url}")

        if confirm:
            # For CLI, the caller should handle confirmation
            # This is just a safety check
            if not os.environ.get("FRECKLE_CONFIRM_SCRIPTS"):
                logger.warning(
                    "Script installation requires confirmation. "
                    "Set FRECKLE_CONFIRM_SCRIPTS=1 to proceed."
                )
                return False

        try:
            # Download script
            curl_result = subprocess.run(
                ["curl", "-fsSL", url],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if curl_result.returncode != 0:
                logger.error(
                    f"Failed to download script: {curl_result.stderr}"
                )
                return False

            # Execute script
            subprocess.run(
                ["sh"],
                input=curl_result.stdout,
                check=True,
                timeout=300,
                text=True,
            )

            return True

        except subprocess.CalledProcessError as e:
            logger.error(f"Script execution failed: {e}")
            return False
        except subprocess.TimeoutExpired:
            logger.error("Script execution timed out")
            return False


def get_tools_from_config(config) -> ToolsRegistry:
    """Create a ToolsRegistry from a Config object."""
    tools_data = config.data.get("tools", {})
    if not isinstance(tools_data, dict):
        tools_data = {}
    return ToolsRegistry(tools_data)
