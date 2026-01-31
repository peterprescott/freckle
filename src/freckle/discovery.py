"""System discovery module for finding installed programs.

Scans the system to discover installed programs from various sources
(Homebrew, Applications, pip/uv, cargo, etc.) and compares them with
the freckle.yaml configuration.
"""

import logging
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set

from .system import Environment

logger = logging.getLogger(__name__)


@dataclass
class DiscoveredProgram:
    """A program discovered on the system."""

    name: str
    source: str  # "brew", "brew_cask", "apt", "cargo", "uv_tool", etc.
    version: Optional[str] = None
    path: Optional[str] = None
    description: Optional[str] = None
    # Whether this was explicitly installed vs. a dependency
    is_dependency: bool = False

    def __hash__(self):
        return hash((self.name, self.source))

    def __eq__(self, other):
        if not isinstance(other, DiscoveredProgram):
            return False
        return self.name == other.name and self.source == other.source


@dataclass
class DiscoveryReport:
    """Report comparing discovered programs with freckle config."""

    # Programs in config and installed
    managed: List[DiscoveredProgram] = field(default_factory=list)
    # Programs installed but not in config
    untracked: List[DiscoveredProgram] = field(default_factory=list)
    # Programs in config but not installed
    missing: List[str] = field(default_factory=list)
    # Scan statistics
    scan_stats: Dict[str, int] = field(default_factory=dict)

    def summary(self) -> str:
        """Generate a summary string."""
        return (
            f"Managed: {len(self.managed)}, "
            f"Untracked: {len(self.untracked)}, "
            f"Missing: {len(self.missing)}"
        )


# Known system packages that shouldn't be suggested for tracking
# These are typically dependencies or system utilities
SYSTEM_PACKAGES: Set[str] = {
    # Core system utilities
    "bash", "sh", "coreutils", "findutils", "grep", "sed", "awk",
    "gzip", "tar", "unzip", "zip", "curl", "wget",
    # Build tools that are typically dependencies
    "autoconf", "automake", "libtool", "pkg-config", "cmake", "make",
    # Common libraries
    "openssl", "libffi", "readline", "ncurses", "gettext", "gmp",
    "libyaml", "libxml2", "libxslt", "pcre", "pcre2", "xz", "zlib",
    "icu4c", "libiconv", "oniguruma", "gdbm", "berkeley-db",
    # Python build deps
    "mpdecimal", "sqlite", "tcl-tk",
    # Git/VCS deps
    "git", "ca-certificates",
}

# Popular tools that are worth suggesting
NOTABLE_TOOLS: Set[str] = {
    # Modern CLI replacements
    "ripgrep", "fd", "bat", "eza", "lsd", "delta", "dust", "duf",
    "bottom", "procs", "sd", "hyperfine", "tokei", "bandwhich",
    "grex", "tealdeer", "zoxide", "broot", "fzf", "atuin",
    # Shell enhancements
    "starship", "fish", "zsh", "nushell",
    # Development tools
    "jq", "yq", "gh", "lazygit", "tig", "difftastic",
    "httpie", "curlie", "xh",
    # Editor/IDE
    "neovim", "helix", "micro",
    # Container/Cloud
    "docker", "podman", "kubectl", "k9s", "helm", "terraform",
    # Programming languages/runtimes
    "node", "python", "ruby", "go", "rust", "deno", "bun",
    # Package managers/version managers
    "uv", "rye", "pyenv", "nvm", "fnm", "rbenv", "mise", "asdf",
    # Other useful tools
    "tmux", "htop", "btop", "ncdu", "tree", "watch", "entr",
    "imagemagick", "ffmpeg", "pandoc",
}


class SystemScanner:
    """Scans the system to discover installed programs."""

    def __init__(self, env: Optional[Environment] = None):
        self.env = env or Environment()
        self._scan_results: Dict[str, List[DiscoveredProgram]] = {}

    def scan_all(
        self,
        include_gui: bool = False,
        sources: Optional[List[str]] = None,
    ) -> List[DiscoveredProgram]:
        """Scan all sources and return discovered programs.

        Args:
            include_gui: Whether to include GUI apps (Applications, casks)
            sources: Specific sources to scan (None = all available)

        Returns:
            List of discovered programs
        """
        results: List[DiscoveredProgram] = []

        # Define available scanners per platform
        if self.env.is_macos():
            scanners = {
                "brew": self._scan_homebrew_formulae,
                "brew_cask": self._scan_homebrew_casks,
                "applications": self._scan_applications,
                "uv_tool": self._scan_uv_tools,
                "cargo": self._scan_cargo,
                "npm": self._scan_npm_global,
                "go": self._scan_go_bin,
            }
        elif self.env.is_linux():
            scanners = {
                "apt": self._scan_apt,
                "snap": self._scan_snap,
                "flatpak": self._scan_flatpak,
                "uv_tool": self._scan_uv_tools,
                "cargo": self._scan_cargo,
                "npm": self._scan_npm_global,
                "go": self._scan_go_bin,
            }
        else:
            scanners = {}

        # Filter to requested sources
        if sources:
            scanners = {k: v for k, v in scanners.items() if k in sources}

        # Skip GUI sources unless requested
        if not include_gui:
            gui_sources = {"brew_cask", "applications", "flatpak", "snap"}
            scanners = {
                k: v for k, v in scanners.items() if k not in gui_sources
            }

        # Run scanners
        for source, scanner in scanners.items():
            try:
                programs = scanner()
                self._scan_results[source] = programs
                results.extend(programs)
            except Exception as e:
                logger.warning(f"Failed to scan {source}: {e}")
                self._scan_results[source] = []

        return results

    def get_scan_stats(self) -> Dict[str, int]:
        """Get counts of programs found per source."""
        return {
            source: len(progs) for source, progs in self._scan_results.items()
        }

    def _run_command(
        self,
        cmd: List[str],
        timeout: int = 30,
    ) -> Optional[str]:
        """Run a command and return stdout, or None on failure."""
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if result.returncode == 0:
                return result.stdout
            return None
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return None

    def _scan_homebrew_formulae(self) -> List[DiscoveredProgram]:
        """Scan Homebrew for installed formulae."""
        if not shutil.which("brew"):
            return []

        programs = []

        # Get list of installed formulae
        output = self._run_command(["brew", "list", "--formula", "-1"])
        if not output:
            return []

        # Get list of explicitly installed (not dependencies)
        leaves_output = self._run_command(["brew", "leaves"])
        if leaves_output:
            leaves = set(leaves_output.strip().split("\n"))
        else:
            leaves = set()

        for name in output.strip().split("\n"):
            if not name:
                continue
            programs.append(DiscoveredProgram(
                name=name,
                source="brew",
                is_dependency=name not in leaves,
            ))

        return programs

    def _scan_homebrew_casks(self) -> List[DiscoveredProgram]:
        """Scan Homebrew for installed casks (GUI apps)."""
        if not shutil.which("brew"):
            return []

        programs = []

        output = self._run_command(["brew", "list", "--cask", "-1"])
        if not output:
            return []

        for name in output.strip().split("\n"):
            if not name:
                continue
            programs.append(DiscoveredProgram(
                name=name,
                source="brew_cask",
            ))

        return programs

    def _scan_applications(self) -> List[DiscoveredProgram]:
        """Scan /Applications and ~/Applications for macOS apps."""
        programs = []

        app_dirs = [
            Path("/Applications"),
            self.env.home / "Applications",
        ]

        for app_dir in app_dirs:
            if not app_dir.exists():
                continue

            for app in app_dir.iterdir():
                if app.suffix == ".app":
                    name = app.stem
                    programs.append(DiscoveredProgram(
                        name=name,
                        source="application",
                        path=str(app),
                    ))

        return programs

    def _scan_uv_tools(self) -> List[DiscoveredProgram]:
        """Scan uv for installed tools."""
        if not shutil.which("uv"):
            return []

        programs = []

        output = self._run_command(["uv", "tool", "list"])
        if not output:
            return []

        # Parse output like:
        # ruff v0.1.0
        #   - ruff
        # mypy v1.0.0
        #   - mypy
        #   - stubgen
        for line in output.strip().split("\n"):
            if not line:
                continue
            # Skip binary entries (indented lines starting with "- ")
            if line.startswith(" "):
                continue
            # Skip lines that are just "-" entries
            if line.strip().startswith("-"):
                continue
            # This is a tool name with version
            parts = line.split()
            if parts and not parts[0].startswith("-"):
                tool_name = parts[0]
                version = parts[1] if len(parts) > 1 else None
                programs.append(DiscoveredProgram(
                    name=tool_name,
                    source="uv_tool",
                    version=version,
                ))

        return programs

    def _scan_cargo(self) -> List[DiscoveredProgram]:
        """Scan cargo for installed crates."""
        if not shutil.which("cargo"):
            return []

        programs = []

        output = self._run_command(["cargo", "install", "--list"])
        if not output:
            return []

        # Parse output like:
        # ripgrep v14.1.0:
        #     rg
        # fd-find v9.0.0:
        #     fd
        for line in output.strip().split("\n"):
            if not line or line.startswith(" "):
                continue
            # Parse "name vX.Y.Z:" format
            if "v" in line and ":" in line:
                parts = line.split()
                if len(parts) >= 2:
                    name = parts[0]
                    version = parts[1].rstrip(":")
                    programs.append(DiscoveredProgram(
                        name=name,
                        source="cargo",
                        version=version,
                    ))

        return programs

    def _scan_npm_global(self) -> List[DiscoveredProgram]:
        """Scan npm for globally installed packages."""
        if not shutil.which("npm"):
            return []

        programs = []

        output = self._run_command(
            ["npm", "list", "-g", "--depth=0", "--json"],
            timeout=60,
        )
        if not output:
            return []

        try:
            import json
            data = json.loads(output)
            deps = data.get("dependencies", {})
            for name, info in deps.items():
                version = (
                    info.get("version") if isinstance(info, dict) else None
                )
                programs.append(DiscoveredProgram(
                    name=name,
                    source="npm",
                    version=version,
                ))
        except (json.JSONDecodeError, KeyError):
            pass

        return programs

    def _scan_go_bin(self) -> List[DiscoveredProgram]:
        """Scan ~/go/bin for Go binaries."""
        programs = []

        go_bin = self.env.home / "go" / "bin"
        if not go_bin.exists():
            return []

        for binary in go_bin.iterdir():
            if binary.is_file() and binary.stat().st_mode & 0o111:
                programs.append(DiscoveredProgram(
                    name=binary.name,
                    source="go",
                    path=str(binary),
                ))

        return programs

    def _scan_apt(self) -> List[DiscoveredProgram]:
        """Scan apt/dpkg for installed packages (Linux only)."""
        if not shutil.which("dpkg"):
            return []

        programs = []

        # Get manually installed packages (not auto-installed deps)
        output = self._run_command(
            ["apt-mark", "showmanual"],
            timeout=60,
        )
        if not output:
            return []

        for name in output.strip().split("\n"):
            if not name:
                continue
            programs.append(DiscoveredProgram(
                name=name,
                source="apt",
            ))

        return programs

    def _scan_snap(self) -> List[DiscoveredProgram]:
        """Scan snap for installed packages (Linux only)."""
        if not shutil.which("snap"):
            return []

        programs = []

        output = self._run_command(["snap", "list"])
        if not output:
            return []

        # Skip header line
        lines = output.strip().split("\n")[1:]
        for line in lines:
            parts = line.split()
            if len(parts) >= 2:
                name = parts[0]
                version = parts[1]
                programs.append(DiscoveredProgram(
                    name=name,
                    source="snap",
                    version=version,
                ))

        return programs

    def _scan_flatpak(self) -> List[DiscoveredProgram]:
        """Scan flatpak for installed packages (Linux only)."""
        if not shutil.which("flatpak"):
            return []

        programs = []

        output = self._run_command(
            ["flatpak", "list", "--app", "--columns=application,version"]
        )
        if not output:
            return []

        for line in output.strip().split("\n"):
            if not line:
                continue
            parts = line.split("\t")
            if parts:
                name = parts[0]
                version = parts[1] if len(parts) > 1 else None
                programs.append(DiscoveredProgram(
                    name=name,
                    source="flatpak",
                    version=version,
                ))

        return programs


def _normalize_name(name: str) -> str:
    """Normalize a program name for fuzzy matching.

    Handles common variations:
    - Case: "Cursor" → "cursor"
    - Spaces/hyphens: "Google Chrome" → "googlechrome"
    - Suffixes: "zoom.us" → "zoom"
    - Common prefixes: removes leading dots
    """
    # Lowercase
    normalized = name.lower()

    # Remove leading dots (e.g., ".Karabiner-VirtualHIDDevice-Manager")
    normalized = normalized.lstrip(".")

    # Remove common suffixes
    for suffix in [".us", ".app", "-app"]:
        if normalized.endswith(suffix):
            normalized = normalized[:-len(suffix)]

    # Remove spaces, hyphens, underscores for comparison
    normalized = normalized.replace(" ", "").replace("-", "").replace("_", "")

    return normalized


def compare_with_config(
    discovered: List[DiscoveredProgram],
    config_tools: Dict[str, dict],
) -> DiscoveryReport:
    """Compare discovered programs with freckle config.

    Args:
        discovered: List of discovered programs
        config_tools: Dict of tool configs from freckle.yaml

    Returns:
        DiscoveryReport with managed, untracked, and missing tools
    """
    # Build normalized lookup tables for fuzzy matching
    # Maps normalized name → original tool name
    tracked_normalized: Dict[str, str] = {}
    package_normalized: Dict[str, str] = {}

    for tool_name, tool_data in config_tools.items():
        # Track the tool name itself (normalized)
        tracked_normalized[_normalize_name(tool_name)] = tool_name

        # Also track package names from install section
        install = tool_data.get("install", {})
        if isinstance(install, dict):
            for pm, package in install.items():
                if isinstance(package, str):
                    package_normalized[_normalize_name(package)] = tool_name

    managed = []
    untracked = []

    for prog in discovered:
        normalized = _normalize_name(prog.name)

        # Check if this program matches any tracked name (fuzzy)
        in_tracked = normalized in tracked_normalized
        in_package = normalized in package_normalized
        if in_tracked or in_package:
            managed.append(prog)
        else:
            untracked.append(prog)

    # Find missing tools (in config but not discovered)
    discovered_names = {p.name for p in discovered}
    discovered_packages = set()

    # Also check package names
    for prog in discovered:
        discovered_packages.add(prog.name)

    missing = []
    for tool_name, tool_data in config_tools.items():
        # Check if tool or any of its packages are installed
        found = tool_name in discovered_names

        if not found:
            install = tool_data.get("install", {})
            if isinstance(install, dict):
                for pm, package in install.items():
                    is_str = isinstance(package, str)
                    if is_str and package in discovered_names:
                        found = True
                        break

        if not found:
            missing.append(tool_name)

    return DiscoveryReport(
        managed=managed,
        untracked=untracked,
        missing=missing,
    )


def filter_notable_tools(
    programs: List[DiscoveredProgram],
    exclude_deps: bool = True,
    exclude_system: bool = True,
) -> List[DiscoveredProgram]:
    """Filter programs to notable/interesting ones.

    Args:
        programs: List of discovered programs
        exclude_deps: Whether to exclude dependency packages
        exclude_system: Whether to exclude known system packages

    Returns:
        Filtered list of programs worth suggesting
    """
    filtered = []

    for prog in programs:
        # Skip dependencies if requested
        if exclude_deps and prog.is_dependency:
            continue

        # Skip system packages if requested
        if exclude_system and prog.name in SYSTEM_PACKAGES:
            continue

        filtered.append(prog)

    return filtered


def get_suggestions(
    untracked: List[DiscoveredProgram],
    max_suggestions: int = 10,
) -> List[DiscoveredProgram]:
    """Get top suggestions from untracked programs.

    Prioritizes notable tools, then sorts by source reliability.

    Args:
        untracked: List of untracked programs
        max_suggestions: Maximum number of suggestions to return

    Returns:
        List of suggested programs to add to config
    """
    # Filter to notable tools first
    notable = [p for p in untracked if p.name in NOTABLE_TOOLS]

    # Then non-dependency, non-system packages
    other = filter_notable_tools(
        [p for p in untracked if p not in notable],
        exclude_deps=True,
        exclude_system=True,
    )

    # Source priority (higher = better)
    source_priority = {
        "brew": 10,
        "brew_cask": 9,
        "cargo": 8,
        "uv_tool": 8,
        "npm": 7,
        "apt": 6,
        "go": 5,
        "snap": 4,
        "flatpak": 3,
        "application": 2,
    }

    def sort_key(prog: DiscoveredProgram) -> tuple:
        is_notable = prog.name in NOTABLE_TOOLS
        priority = source_priority.get(prog.source, 0)
        return (-int(is_notable), -priority, prog.name)

    combined = notable + other
    combined.sort(key=sort_key)

    return combined[:max_suggestions]


def generate_yaml_snippet(programs: List[DiscoveredProgram]) -> str:
    """Generate YAML snippet for adding programs to freckle.yaml.

    Args:
        programs: List of programs to generate config for

    Returns:
        YAML string that can be added to freckle.yaml
    """
    lines = ["tools:"]

    for prog in programs:
        lines.append(f"  {prog.name}:")

        if prog.description:
            lines.append(f"    description: {prog.description}")

        lines.append("    install:")

        # Map source to install config
        if prog.source == "brew":
            lines.append(f"      brew: {prog.name}")
        elif prog.source == "brew_cask":
            lines.append(f"      brew_cask: {prog.name}")
        elif prog.source == "cargo":
            lines.append(f"      cargo: {prog.name}")
        elif prog.source == "uv_tool":
            lines.append(f"      uv_tool: {prog.name}")
        elif prog.source == "npm":
            lines.append(f"      npm: {prog.name}")
        elif prog.source == "apt":
            lines.append(f"      apt: {prog.name}")
        elif prog.source == "snap":
            lines.append(f"      snap: {prog.name}")
        else:
            lines.append(f"      # {prog.source}: {prog.name}")

        # Add verify command based on source
        if prog.source in ("brew", "apt", "cargo", "uv_tool"):
            lines.append(f"    verify: {prog.name} --version")

        lines.append("")

    return "\n".join(lines)
