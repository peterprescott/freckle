"""Discover command for finding installed programs on the system."""

from typing import List, Optional

import typer

from ..discovery import (
    DiscoveredProgram,
    SystemScanner,
    compare_with_config,
    filter_notable_tools,
    generate_yaml_snippet,
    get_suggestions,
)
from .helpers import get_config
from .output import (
    console,
    error,
    header,
    info,
    muted,
    plain,
    success,
    warning,
)


def register(app: typer.Typer) -> None:
    """Register the discover command with the app."""
    app.command()(discover)


def discover(
    source: Optional[List[str]] = typer.Option(
        None,
        "--source",
        "-s",
        help="Specific sources to scan (brew, cargo, uv_tool, npm, go, apt, snap)",
    ),
    include_gui: bool = typer.Option(
        False,
        "--gui",
        "-g",
        help="Include GUI apps (Applications, brew casks, flatpak)",
    ),
    untracked: bool = typer.Option(
        False,
        "--untracked",
        "-u",
        help="Only show programs not in freckle.yaml",
    ),
    suggest: bool = typer.Option(
        False,
        "--suggest",
        help="Show top suggestions for tools to add",
    ),
    format_: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format: table, yaml, json",
    ),
    all_: bool = typer.Option(
        False,
        "--all",
        "-a",
        help="Show all programs including dependencies",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show detailed output",
    ),
):
    """Discover installed programs on your system.

    Scans various package managers and sources to find installed programs,
    then compares with your freckle.yaml configuration.

    Examples:
        freckle discover              # Scan CLI tools
        freckle discover --gui        # Include GUI apps
        freckle discover --untracked  # Only untracked programs
        freckle discover --suggest    # Get suggestions
        freckle discover -s brew      # Only scan Homebrew
        freckle discover --format yaml  # Output as YAML snippet
    """
    scanner = SystemScanner()

    # Show scanning progress
    if format_ == "table":
        plain("Scanning system...")

    # Perform scan
    discovered = scanner.scan_all(
        include_gui=include_gui,
        sources=source,
    )

    # Get scan stats
    stats = scanner.get_scan_stats()

    # Show scan summary
    if format_ == "table" and stats:
        for src, count in stats.items():
            if count > 0:
                success(f"{src}: {count} programs", prefix="  ✓")
            elif verbose:
                muted(f"  - {src}: 0 programs")

    # Load config and compare
    try:
        config = get_config()
        config_tools = config.data.get("tools", {})
    except Exception:
        config_tools = {}

    report = compare_with_config(discovered, config_tools)
    report.scan_stats = stats

    # Filter results based on options
    if not all_:
        # Filter out dependencies and system packages
        report.untracked = filter_notable_tools(
            report.untracked,
            exclude_deps=True,
            exclude_system=True,
        )

    # Output based on format and options
    if format_ == "json":
        _output_json(report, untracked_only=untracked)
    elif format_ == "yaml":
        _output_yaml(report, untracked_only=untracked)
    else:
        _output_table(
            report,
            untracked_only=untracked,
            show_suggestions=suggest,
            verbose=verbose,
        )


def _output_table(
    report,
    untracked_only: bool,
    show_suggestions: bool,
    verbose: bool,
) -> None:
    """Output discovery results as a formatted table."""
    plain("")
    header("Summary")
    plain(f"  Managed by freckle:     {len(report.managed)}")
    plain(f"  Installed, not tracked: {len(report.untracked)}")

    # Show untracked tools
    if not untracked_only or report.untracked:
        plain("")
        header("Untracked Programs")

        if not report.untracked:
            success("All discovered programs are tracked!", prefix="  ✓")
        else:
            if show_suggestions:
                suggestions = get_suggestions(report.untracked, max_suggestions=15)
                muted("  Top suggestions to add to freckle.yaml:")
                plain("")

                for prog in suggestions:
                    _print_program(prog, verbose)

                if len(report.untracked) > len(suggestions):
                    remaining = len(report.untracked) - len(suggestions)
                    plain("")
                    muted(f"  ... and {remaining} more programs")
                    muted("  Run with --all to see everything")
            else:
                # Group by source
                by_source = {}
                for prog in report.untracked:
                    by_source.setdefault(prog.source, []).append(prog)

                for src, progs in sorted(by_source.items()):
                    plain(f"  {src} ({len(progs)}):")
                    for prog in progs[:5]:
                        _print_program(prog, verbose, indent=4)
                    if len(progs) > 5:
                        muted(f"      ... and {len(progs) - 5} more")
                    plain("")

    # Show managed tools (if verbose or not filtering)
    if verbose and not untracked_only and report.managed:
        plain("")
        header("Managed Tools")
        for prog in report.managed[:10]:
            success(f"{prog.name} ({prog.source})", prefix="  ✓")
        if len(report.managed) > 10:
            muted(f"  ... and {len(report.managed) - 10} more")

    # Show next steps
    if report.untracked and not show_suggestions:
        plain("")
        info("  Tip: Run 'freckle discover --suggest' to see recommendations")
    elif report.untracked and show_suggestions:
        plain("")
        info("  Tip: Run 'freckle discover --format yaml' to generate config")


def _print_program(
    prog: DiscoveredProgram,
    verbose: bool,
    indent: int = 2,
) -> None:
    """Print a single program line."""
    spaces = " " * indent
    version_str = f" ({prog.version})" if prog.version else ""
    source_str = f"[{prog.source}]"

    if verbose and prog.path:
        plain(f"{spaces}• {prog.name}{version_str} {source_str}")
        muted(f"{spaces}    {prog.path}")
    else:
        plain(f"{spaces}• {prog.name}{version_str} {source_str}")


def _output_yaml(report, untracked_only: bool) -> None:
    """Output discovery results as YAML snippet."""
    programs = report.untracked if untracked_only else report.untracked

    if not programs:
        console.print("# No untracked programs to add")
        return

    # Get suggestions for cleaner output
    suggestions = get_suggestions(programs, max_suggestions=50)

    console.print("# Discovered tools not in freckle.yaml")
    console.print(f"# Generated by: freckle discover --format yaml")
    console.print("")
    console.print(generate_yaml_snippet(suggestions))


def _output_json(report, untracked_only: bool) -> None:
    """Output discovery results as JSON."""
    import json

    data = {
        "summary": {
            "managed": len(report.managed),
            "untracked": len(report.untracked),
        },
        "scan_stats": report.scan_stats,
    }

    if untracked_only:
        data["programs"] = [
            {
                "name": p.name,
                "source": p.source,
                "version": p.version,
                "path": p.path,
            }
            for p in report.untracked
        ]
    else:
        data["managed"] = [
            {"name": p.name, "source": p.source}
            for p in report.managed
        ]
        data["untracked"] = [
            {
                "name": p.name,
                "source": p.source,
                "version": p.version,
            }
            for p in report.untracked
        ]

    console.print(json.dumps(data, indent=2))
