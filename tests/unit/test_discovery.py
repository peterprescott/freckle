"""Unit tests for the discovery module."""

import pytest

from freckle.discovery import (
    DiscoveredProgram,
    DiscoveryReport,
    NOTABLE_TOOLS,
    SYSTEM_PACKAGES,
    SystemScanner,
    _normalize_name,
    compare_with_config,
    filter_notable_tools,
    generate_yaml_snippet,
    get_suggestions,
)
from freckle.system import Environment, OS


class TestDiscoveredProgram:
    """Tests for the DiscoveredProgram dataclass."""

    def test_basic_creation(self):
        """Test creating a basic DiscoveredProgram."""
        prog = DiscoveredProgram(name="ripgrep", source="brew")
        assert prog.name == "ripgrep"
        assert prog.source == "brew"
        assert prog.version is None
        assert prog.path is None
        assert prog.is_dependency is False

    def test_with_all_fields(self):
        """Test creating a DiscoveredProgram with all fields."""
        prog = DiscoveredProgram(
            name="fd",
            source="cargo",
            version="v9.0.0",
            path="/home/user/.cargo/bin/fd",
            description="Fast find alternative",
            is_dependency=False,
        )
        assert prog.name == "fd"
        assert prog.version == "v9.0.0"
        assert prog.path == "/home/user/.cargo/bin/fd"

    def test_hash_and_equality(self):
        """Test that DiscoveredPrograms can be used in sets."""
        prog1 = DiscoveredProgram(name="rg", source="brew")
        prog2 = DiscoveredProgram(name="rg", source="brew", version="14.0")
        prog3 = DiscoveredProgram(name="rg", source="cargo")

        # Same name and source = equal
        assert prog1 == prog2
        assert hash(prog1) == hash(prog2)

        # Different source = not equal
        assert prog1 != prog3

        # Can be used in sets
        programs = {prog1, prog2, prog3}
        assert len(programs) == 2  # prog1 and prog2 are duplicates


class TestDiscoveryReport:
    """Tests for the DiscoveryReport dataclass."""

    def test_empty_report(self):
        """Test creating an empty report."""
        report = DiscoveryReport()
        assert report.managed == []
        assert report.untracked == []
        assert report.missing == []
        assert report.summary() == "Managed: 0, Untracked: 0, Missing: 0"

    def test_report_with_data(self):
        """Test report summary with data."""
        report = DiscoveryReport(
            managed=[
                DiscoveredProgram(name="ripgrep", source="brew"),
                DiscoveredProgram(name="fd", source="brew"),
            ],
            untracked=[
                DiscoveredProgram(name="abcde", source="brew"),
            ],
            missing=["delta", "bat"],
        )
        assert report.summary() == "Managed: 2, Untracked: 1, Missing: 2"


class TestCompareWithConfig:
    """Tests for the compare_with_config function."""

    def test_empty_inputs(self):
        """Test with no discovered programs and no config."""
        report = compare_with_config([], {})
        assert report.managed == []
        assert report.untracked == []
        assert report.missing == []

    def test_all_managed(self):
        """Test when all discovered programs are in config."""
        discovered = [
            DiscoveredProgram(name="ripgrep", source="brew"),
            DiscoveredProgram(name="fd", source="brew"),
        ]
        config_tools = {
            "ripgrep": {"install": {"brew": "ripgrep"}},
            "fd": {"install": {"brew": "fd"}},
        }
        report = compare_with_config(discovered, config_tools)

        assert len(report.managed) == 2
        assert len(report.untracked) == 0
        assert len(report.missing) == 0

    def test_all_untracked(self):
        """Test when no discovered programs are in config."""
        discovered = [
            DiscoveredProgram(name="imagemagick", source="brew"),
            DiscoveredProgram(name="nvm", source="brew"),
        ]
        config_tools = {
            "ripgrep": {"install": {"brew": "ripgrep"}},
        }
        report = compare_with_config(discovered, config_tools)

        assert len(report.managed) == 0
        assert len(report.untracked) == 2
        assert "ripgrep" in report.missing

    def test_mixed_managed_and_untracked(self):
        """Test with a mix of managed and untracked programs."""
        discovered = [
            DiscoveredProgram(name="ripgrep", source="brew"),
            DiscoveredProgram(name="imagemagick", source="brew"),
        ]
        config_tools = {
            "ripgrep": {"install": {"brew": "ripgrep"}},
            "fd": {"install": {"brew": "fd"}},
        }
        report = compare_with_config(discovered, config_tools)

        assert len(report.managed) == 1
        assert report.managed[0].name == "ripgrep"
        assert len(report.untracked) == 1
        assert report.untracked[0].name == "imagemagick"
        assert "fd" in report.missing

    def test_package_name_mapping(self):
        """Test that package names in install section are mapped correctly."""
        discovered = [
            DiscoveredProgram(name="git-delta", source="brew"),
        ]
        config_tools = {
            "delta": {"install": {"brew": "git-delta"}},
        }
        report = compare_with_config(discovered, config_tools)

        # git-delta should be recognized as managed because delta uses brew: git-delta
        assert len(report.managed) == 1
        assert report.managed[0].name == "git-delta"
        assert len(report.missing) == 0

    def test_simple_install_string(self):
        """Test with simple install string (not dict)."""
        discovered = [
            DiscoveredProgram(name="jq", source="brew"),
        ]
        config_tools = {
            "jq": {"install": "jq"},  # Simple string form
        }
        # Simple string form is converted to dict by ToolDefinition
        # but our comparison handles the raw dict from config
        report = compare_with_config(discovered, config_tools)

        # Name matches directly
        assert len(report.managed) == 1


class TestFilterNotableTools:
    """Tests for the filter_notable_tools function."""

    def test_excludes_dependencies(self):
        """Test that dependencies are excluded by default."""
        programs = [
            DiscoveredProgram(name="ripgrep", source="brew", is_dependency=False),
            DiscoveredProgram(name="openssl", source="brew", is_dependency=True),
        ]
        filtered = filter_notable_tools(programs)

        assert len(filtered) == 1
        assert filtered[0].name == "ripgrep"

    def test_excludes_system_packages(self):
        """Test that known system packages are excluded."""
        programs = [
            DiscoveredProgram(name="ripgrep", source="brew"),
            DiscoveredProgram(name="curl", source="brew"),
            DiscoveredProgram(name="coreutils", source="brew"),
        ]
        filtered = filter_notable_tools(programs)

        assert len(filtered) == 1
        assert filtered[0].name == "ripgrep"

    def test_include_dependencies_when_requested(self):
        """Test that dependencies can be included."""
        programs = [
            DiscoveredProgram(name="ripgrep", source="brew", is_dependency=False),
            DiscoveredProgram(name="openssl", source="brew", is_dependency=True),
        ]
        filtered = filter_notable_tools(programs, exclude_deps=False)

        # openssl is in SYSTEM_PACKAGES so still excluded
        assert len(filtered) == 1

    def test_include_system_when_requested(self):
        """Test that system packages can be included."""
        programs = [
            DiscoveredProgram(name="curl", source="brew"),
        ]
        filtered = filter_notable_tools(programs, exclude_system=False)

        assert len(filtered) == 1
        assert filtered[0].name == "curl"


class TestGetSuggestions:
    """Tests for the get_suggestions function."""

    def test_prioritizes_notable_tools(self):
        """Test that notable tools are prioritized."""
        programs = [
            DiscoveredProgram(name="abcde", source="brew"),  # Not notable
            DiscoveredProgram(name="ripgrep", source="brew"),  # Notable
            DiscoveredProgram(name="xyz123", source="brew"),  # Not notable
            DiscoveredProgram(name="fzf", source="brew"),  # Notable
        ]
        suggestions = get_suggestions(programs, max_suggestions=3)

        # Notable tools should come first
        assert suggestions[0].name in NOTABLE_TOOLS
        assert suggestions[1].name in NOTABLE_TOOLS

    def test_respects_max_suggestions(self):
        """Test that max_suggestions is respected."""
        programs = [
            DiscoveredProgram(name=f"tool{i}", source="brew")
            for i in range(20)
        ]
        suggestions = get_suggestions(programs, max_suggestions=5)

        assert len(suggestions) == 5

    def test_empty_list(self):
        """Test with empty input."""
        suggestions = get_suggestions([])
        assert suggestions == []


class TestGenerateYamlSnippet:
    """Tests for the generate_yaml_snippet function."""

    def test_generates_valid_yaml(self):
        """Test that generated YAML is valid."""
        programs = [
            DiscoveredProgram(name="ripgrep", source="brew"),
        ]
        yaml_str = generate_yaml_snippet(programs)

        assert "tools:" in yaml_str
        assert "ripgrep:" in yaml_str
        assert "brew: ripgrep" in yaml_str
        assert "verify: ripgrep --version" in yaml_str

    def test_different_sources(self):
        """Test YAML generation for different sources."""
        programs = [
            DiscoveredProgram(name="ruff", source="uv_tool"),
            DiscoveredProgram(name="fd-find", source="cargo"),
            DiscoveredProgram(name="typescript", source="npm"),
        ]
        yaml_str = generate_yaml_snippet(programs)

        assert "uv_tool: ruff" in yaml_str
        assert "cargo: fd-find" in yaml_str
        assert "npm: typescript" in yaml_str

    def test_includes_description(self):
        """Test that descriptions are included when present."""
        programs = [
            DiscoveredProgram(
                name="ripgrep",
                source="brew",
                description="Fast grep alternative",
            ),
        ]
        yaml_str = generate_yaml_snippet(programs)

        assert "description: Fast grep alternative" in yaml_str


class TestSystemScanner:
    """Tests for the SystemScanner class."""

    def test_scanner_creation(self):
        """Test creating a scanner."""
        scanner = SystemScanner()
        assert scanner.env is not None

    def test_scanner_with_custom_env(self):
        """Test creating a scanner with custom environment."""
        env = Environment()
        scanner = SystemScanner(env=env)
        assert scanner.env is env

    def test_get_scan_stats_empty(self):
        """Test scan stats before scanning."""
        scanner = SystemScanner()
        stats = scanner.get_scan_stats()
        assert stats == {}


class TestNormalizeName:
    """Tests for the _normalize_name function."""

    def test_lowercase(self):
        """Test that names are lowercased."""
        assert _normalize_name("Cursor") == "cursor"
        assert _normalize_name("SLACK") == "slack"

    def test_removes_spaces_and_hyphens(self):
        """Test that spaces and hyphens are removed."""
        assert _normalize_name("Google Chrome") == "googlechrome"
        assert _normalize_name("visual-studio-code") == "visualstudiocode"
        assert _normalize_name("Karabiner-Elements") == "karabinerelements"

    def test_removes_suffixes(self):
        """Test that common suffixes are removed."""
        assert _normalize_name("zoom.us") == "zoom"
        assert _normalize_name("myapp.app") == "myapp"

    def test_removes_leading_dots(self):
        """Test that leading dots are removed."""
        assert _normalize_name(".hidden-tool") == "hiddentool"

    def test_combined_normalization(self):
        """Test normalization with multiple transformations."""
        # .app suffix removed, then hyphens removed
        assert _normalize_name("My-Cool-Tool.app") == "mycooltool"
        assert _normalize_name(".Karabiner-VirtualHIDDevice-Manager") == "karabinervirtualhiddevicemanager"


class TestCompareWithConfigFuzzyMatching:
    """Tests for fuzzy matching in compare_with_config."""

    def test_case_insensitive_matching(self):
        """Test that matching is case-insensitive."""
        discovered = [
            DiscoveredProgram(name="Cursor", source="application"),
            DiscoveredProgram(name="SLACK", source="application"),
        ]
        config_tools = {
            "cursor": {"install": {"brew_cask": "cursor"}},
            "slack": {"install": {"brew_cask": "slack"}},
        }
        report = compare_with_config(discovered, config_tools)

        assert len(report.managed) == 2
        assert len(report.untracked) == 0

    def test_matches_with_spaces(self):
        """Test that names with spaces match hyphenated config names."""
        discovered = [
            DiscoveredProgram(name="Google Chrome", source="application"),
        ]
        config_tools = {
            "chrome": {"install": {"brew_cask": "google-chrome"}},
        }
        report = compare_with_config(discovered, config_tools)

        # "Google Chrome" normalized = "googlechrome"
        # "google-chrome" normalized = "googlechrome"
        assert len(report.managed) == 1

    def test_matches_zoom_suffix(self):
        """Test that zoom.us matches zoom."""
        discovered = [
            DiscoveredProgram(name="zoom.us", source="application"),
        ]
        config_tools = {
            "zoom": {"install": {"brew_cask": "zoom"}},
        }
        report = compare_with_config(discovered, config_tools)

        assert len(report.managed) == 1


class TestConstants:
    """Tests for module constants."""

    def test_notable_tools_not_empty(self):
        """Test that NOTABLE_TOOLS is populated."""
        assert len(NOTABLE_TOOLS) > 0
        assert "ripgrep" in NOTABLE_TOOLS
        assert "fzf" in NOTABLE_TOOLS

    def test_system_packages_not_empty(self):
        """Test that SYSTEM_PACKAGES is populated."""
        assert len(SYSTEM_PACKAGES) > 0
        assert "curl" in SYSTEM_PACKAGES
        assert "openssl" in SYSTEM_PACKAGES

    def test_no_overlap_notable_and_system(self):
        """Test that notable tools aren't in system packages."""
        overlap = NOTABLE_TOOLS & SYSTEM_PACKAGES
        # There shouldn't be overlap (notable tools shouldn't be filtered out)
        assert len(overlap) == 0, f"Unexpected overlap: {overlap}"
