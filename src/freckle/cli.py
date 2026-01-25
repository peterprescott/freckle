"""Command-line interface for freckle - keep track of all your dot(file)s."""

import logging
import shutil
import subprocess
from pathlib import Path

import fire
import yaml

from .config import Config
from .dotfiles import DotfilesManager
from .environment import Environment
from .managers.nvim import NvimManager
from .managers.tmux import TmuxManager
from .managers.zsh import ZshManager
from .system import SystemPackageManager
from .utils import (
    get_version,
    setup_logging,
    validate_git_url,
    verify_git_url_accessible,
)


class FreckleCLI:
    """Freckle CLI - keep track of all your dot(file)s."""
    
    def __init__(self):
        setup_logging()
        self.env = Environment()
        self.logger = logging.getLogger(__name__)

    def __call__(self, repo: str = None, branch: str = None, backup: bool = False, update: bool = False) -> int:
        """Default action - runs the freckle sync sequence.
        
        Args:
            repo: Override dotfiles repository URL.
            branch: Override git branch.
            backup: Commit and push local changes.
            update: Pull and apply remote changes (discards local changes).
            
        Returns:
            Exit code (0 for success, 1 for failure).
        """
        return self.run(repo=repo, branch=branch, backup=backup, update=update)

    def init(self, force: bool = False) -> int:
        """Initialize configuration and set up dotfiles repository.
        
        Offers two modes:
        1. Clone an existing dotfiles repository
        2. Create a new dotfiles repository from scratch
        
        Args:
            force: Overwrite existing configuration if present.
            
        Returns:
            Exit code (0 for success, 1 for failure).
        """
        config_path = self.env.home / ".freckle.yaml"
        
        if config_path.exists() and not force:
            self.logger.error(f"Config file already exists at {config_path}. Use --force to overwrite.")
            return 1

        print("--- freckle Initialization ---\n")
        
        # Ask if they have an existing repo
        choice = input("Do you have an existing dotfiles repository? [y/N]: ").strip().lower()
        
        if choice in ["y", "yes"]:
            return self._init_clone_existing(config_path)
        else:
            return self._init_create_new(config_path)

    def _init_clone_existing(self, config_path: Path) -> int:
        """Initialize by cloning an existing dotfiles repo."""
        print("\n--- Clone Existing Repository ---\n")
        
        # Get and validate repository URL
        while True:
            repo_url = input("Enter your dotfiles repository URL: ").strip()
            
            if not repo_url:
                print("  Repository URL is required.")
                continue
            
            if not validate_git_url(repo_url):
                print("  Invalid URL format. Please enter a valid git URL.")
                print("  Examples: https://github.com/user/repo.git")
                print("            git@github.com:user/repo.git")
                continue
            
            # Try to verify the URL is accessible
            print("  Verifying repository access...")
            accessible, error = verify_git_url_accessible(repo_url)
            if not accessible:
                print(f"  Warning: Could not access repository: {error}")
                confirm = input("  Continue anyway? [y/N]: ").strip().lower()
                if confirm not in ["y", "yes"]:
                    continue
            else:
                print("  ✓ Repository accessible")
            
            break
        
        branch = input("Enter your preferred branch (default: main): ").strip().lower() or "main"
        dotfiles_dir = input("Enter directory for bare repo (default: .dotfiles): ").strip() or ".dotfiles"

        config_data = {
            "dotfiles": {
                "repo_url": repo_url,
                "branch": branch,
                "dir": dotfiles_dir
            },
            "modules": ["dotfiles", "zsh", "tmux", "nvim"]
        }

        with open(config_path, "w") as f:
            yaml.dump(config_data, f, default_flow_style=False)
        
        self.logger.info(f"Created configuration at {config_path}")
        print("\n✓ Configuration saved! Run 'freckle run' to clone and set up your dotfiles.")
        return 0

    def _init_create_new(self, config_path: Path) -> int:
        """Initialize by creating a new dotfiles repo."""
        print("\n--- Create New Dotfiles Repository ---\n")
        
        repo_url = ""
        
        # Check if gh CLI is available
        has_gh = shutil.which("gh") is not None
        
        if has_gh:
            print("GitHub CLI detected. Create a new repo on GitHub?")
            create_gh = input("Create repo with 'gh repo create'? [Y/n]: ").strip().lower()
            
            if create_gh not in ["n", "no"]:
                repo_name = input("Repository name (default: dotfiles): ").strip() or "dotfiles"
                private = input("Make it private? [Y/n]: ").strip().lower()
                visibility = "--private" if private not in ["n", "no"] else "--public"
                
                print(f"\n  Creating {repo_name} on GitHub...")
                try:
                    result = subprocess.run(
                        ["gh", "repo", "create", repo_name, visibility, "--confirm"],
                        capture_output=True,
                        text=True,
                        timeout=30
                    )
                    if result.returncode == 0:
                        # Extract URL from output or construct it
                        # gh repo create outputs the URL
                        repo_url = result.stdout.strip()
                        if not repo_url:
                            # Fallback: construct URL from gh config
                            user_result = subprocess.run(
                                ["gh", "api", "user", "-q", ".login"],
                                capture_output=True, text=True
                            )
                            if user_result.returncode == 0:
                                username = user_result.stdout.strip()
                                repo_url = f"https://github.com/{username}/{repo_name}.git"
                        print(f"  ✓ Created: {repo_url}")
                    else:
                        print(f"  ✗ Failed: {result.stderr.strip()}")
                        print("  Continuing without remote.")
                except Exception as e:
                    print(f"  ✗ Error: {e}")
                    print("  Continuing without remote.")
        
        # If we don't have a URL yet, ask for one
        if not repo_url:
            if not has_gh:
                print("To sync across machines, you'll need a remote repository.")
                print("Create one on GitHub/GitLab, then enter the URL here.")
                print("Or leave blank to set up locally only.\n")
            else:
                print("\nEnter repository URL, or blank to skip:\n")
            
            while True:
                url_input = input("Repository URL (or blank): ").strip()
                
                if not url_input:
                    break
                
                if not validate_git_url(url_input):
                    print("  Warning: URL format looks unusual.")
                
                print("  Checking repository access...")
                accessible, error = verify_git_url_accessible(url_input)
                if not accessible:
                    print(f"  ✗ Cannot access repository: {error}")
                    retry = input("  Try a different URL? [Y/n]: ").strip().lower()
                    if retry in ["n", "no"]:
                        break
                    continue
                else:
                    print("  ✓ Repository accessible")
                    repo_url = url_input
                    break
        
        branch = input("Enter branch name (default: main): ").strip().lower() or "main"
        dotfiles_dir = input("Enter directory for bare repo (default: .dotfiles): ").strip() or ".dotfiles"
        
        # Ask which files to track initially
        print("\nWhich dotfiles do you want to track? (Enter comma-separated list)")
        print("Examples: .zshrc, .bashrc, .gitconfig, .tmux.conf, .config/nvim")
        print("Or press Enter for common defaults: .freckle.yaml, .zshrc, .gitconfig, .tmux.conf\n")
        
        files_input = input("Files to track: ").strip()
        if files_input:
            initial_files = [f.strip() for f in files_input.split(",") if f.strip()]
            # Always include .freckle.yaml
            if ".freckle.yaml" not in initial_files:
                initial_files.insert(0, ".freckle.yaml")
        else:
            initial_files = [".freckle.yaml", ".zshrc", ".gitconfig", ".tmux.conf"]
        
        # Check if dotfiles directory already exists
        # Resolve relative paths against home directory
        dotfiles_path = Path(dotfiles_dir).expanduser()
        if not dotfiles_path.is_absolute():
            dotfiles_path = self.env.home / dotfiles_path
        if dotfiles_path.exists():
            print(f"\n⚠ Directory already exists: {dotfiles_path}")
            choice = input("Remove it and start fresh? [y/N]: ").strip().lower()
            if choice in ["y", "yes"]:
                shutil.rmtree(dotfiles_path)
                print(f"  Removed {dotfiles_path}")
            else:
                print("  Aborting. Remove the directory manually or choose a different location.")
                return 1
        
        # Save config FIRST so it can be included in the initial commit
        config_data = {
            "dotfiles": {
                "repo_url": repo_url or f"file://{dotfiles_path}",
                "branch": branch,
                "dir": dotfiles_dir
            },
            "modules": ["dotfiles", "zsh", "tmux", "nvim"]
        }

        with open(config_path, "w") as f:
            yaml.dump(config_data, f, default_flow_style=False)
        
        self.logger.info(f"Created configuration at {config_path}")
        
        # Now .freckle.yaml exists, re-check which files exist
        all_files_to_track = []
        for f in initial_files:
            path = self.env.home / f
            if path.exists():
                all_files_to_track.append(f)
            else:
                print(f"  Note: {f} doesn't exist yet, skipping")
        
        if not all_files_to_track:
            print("\nNo existing files to track. You can add files later with:")
            print(f"  git --git-dir=~/{dotfiles_dir} --work-tree=~ add <file>")
        
        # Create the repo
        dotfiles = DotfilesManager(repo_url or "", dotfiles_path, self.env.home, branch)
        
        try:
            dotfiles.create_new(initial_files=all_files_to_track, remote_url=repo_url or None)
            print(f"\n✓ Created new dotfiles repository at {dotfiles_dir}")
            
            if all_files_to_track:
                print(f"✓ Tracking {len(all_files_to_track)} file(s): {', '.join(all_files_to_track)}")
        except Exception as e:
            self.logger.error(f"Failed to create repository: {e}")
            # Clean up the config file we created
            config_path.unlink(missing_ok=True)
            return 1
        
        if repo_url:
            print("\nNext steps:")
            print("  1. Run 'freckle run --backup' to push your dotfiles")
            print("  2. On other machines, run 'freckle init' and choose option 1")
        else:
            print("\nNext steps:")
            print("  1. Create a repo on GitHub/GitLab")
            print(f"  2. Add remote: git --git-dir={dotfiles_dir} remote add origin <url>")
            print("  3. Push: git --git-dir={dotfiles_dir} push -u origin main")
        
        return 0

    def run(self, repo: str = None, branch: str = None, backup: bool = False, update: bool = False) -> int:
        """Run the freckle sync sequence.
        
        Args:
            repo: Override dotfiles repository URL.
            branch: Override git branch.
            backup: Commit and push local changes.
            update: Pull and apply remote changes (discards local changes).
            
        Returns:
            Exit code (0 for success, 1 for failure).
        """
        config_path = self.env.home / ".freckle.yaml"
        config = Config(config_path, env=self.env)
        
        # Override from CLI
        if repo:
            if not validate_git_url(repo):
                self.logger.error(f"Invalid repository URL: {repo}")
                return 1
            config.data["dotfiles"]["repo_url"] = repo
        if branch:
            config.data["dotfiles"]["branch"] = branch

        repo_url = config.get("dotfiles.repo_url")
        if not repo_url:
            self.logger.error("No dotfiles repository URL found. Run 'freckle init' first or use --repo.")
            return 1

        dotfiles_dir = Path(config.get("dotfiles.dir")).expanduser()
        if not dotfiles_dir.is_absolute():
            dotfiles_dir = self.env.home / dotfiles_dir
        branch = config.get("dotfiles.branch")
        work_tree = self.env.home
        enabled_modules = config.get("modules", [])

        is_first_run = not dotfiles_dir.exists()
        action_name = "Setup" if is_first_run else "Sync"
        
        print(f"\n--- freckle {action_name} ---")
        print(f"Platform: {self.env.os_info['pretty_name']}")
        
        pkg_mgr = SystemPackageManager(self.env)
        
        # Initialize managers
        dotfiles = DotfilesManager(repo_url, dotfiles_dir, work_tree, branch)
        tool_managers = [
            ZshManager(self.env, pkg_mgr),
            TmuxManager(self.env, pkg_mgr),
            NvimManager(self.env, pkg_mgr)
        ]

        try:
            if "dotfiles" in enabled_modules:
                if is_first_run:
                    print(f"[*] Initial setup of dotfiles from {repo_url}...")
                    dotfiles.setup()
                else:
                    report = dotfiles.get_detailed_status()
                    
                    if report.get("fetch_failed"):
                        print("⚠ Could not connect to remote (offline mode)")
                    
                    local_changes = report["has_local_changes"]
                    is_behind = report.get("is_behind", False)
                    is_ahead = report.get("is_ahead", False)

                    if not local_changes and not is_behind and not is_ahead:
                        print("✓ Dotfiles are up-to-date.")
                    elif local_changes and not is_behind:
                        # Local uncommitted changes, not behind remote
                        print("⚠ You have local changes that are not backed up:")
                        for f in report["changed_files"]:
                            print(f"    - {f}")
                        
                        if is_ahead:
                            print(f"\n  (Local is {report.get('ahead_count', 0)} commit(s) ahead of remote)")
                        
                        if backup:
                            msg = f"Automated backup from {self.env.os_info['pretty_name']}"
                            result = dotfiles.commit_and_push(msg)
                            if result["success"]:
                                print("✓ Changes backed up successfully")
                            elif result["committed"] and not result["pushed"]:
                                print(f"⚠ Changes committed locally but push failed: {result['error']}")
                            else:
                                print(f"✗ Backup failed: {result['error']}")
                        else:
                            print("\nTo backup these changes, run: freckle run --backup")
                            return 0
                    elif not local_changes and is_behind:
                        # Remote has updates, no local uncommitted changes
                        behind_count = report.get('behind_count', 0)
                        print(f"↓ Remote repository ({branch}) has {behind_count} new commit(s).")
                        if update:
                            dotfiles.force_checkout()
                            print("✓ Updated to latest remote version")
                        else:
                            print("\nTo update your local files, run: freckle run --update")
                            return 0
                    elif local_changes and is_behind:
                        # Conflict: both local changes and remote updates
                        print("‼ CONFLICT: You have local changes AND remote has new commits.")
                        print(f"  Local Commit : {report['local_commit']}")
                        print(f"  Remote Commit: {report['remote_commit']}")
                        print(f"  Behind by: {report.get('behind_count', 0)} commit(s)")
                        
                        print("\nLocal changes:")
                        for f in report["changed_files"]:
                            print(f"    - {f}")
                            
                        if backup:
                            msg = "Manual backup during conflict"
                            result = dotfiles.commit_and_push(msg)
                            if result["success"]:
                                print("✓ Local changes backed up (you may need to merge/rebase)")
                            else:
                                print(f"⚠ Backup issue: {result['error']}")
                        elif update:
                            dotfiles.force_checkout()
                            print("✓ Discarded local changes and updated to remote")
                        else:
                            print("\nOptions to resolve conflict:")
                            print("  - To keep local changes and backup: freckle run --backup")
                            print("  - To discard local changes and update: freckle run --update")
                            return 0
                    elif is_ahead and not local_changes:
                        # Local has commits not on remote
                        ahead_count = report.get('ahead_count', 0)
                        print(f"↑ Local is {ahead_count} commit(s) ahead of remote.")
                        if backup:
                            result = dotfiles.push()
                            if result["success"]:
                                print("✓ Pushed to remote")
                            else:
                                print(f"✗ Push failed: {result['error']}")
                        else:
                            print("\nTo push, run: freckle run --backup")
                            return 0
                    elif report.get("remote_branch_missing") and not local_changes:
                        # Local branch exists but remote doesn't (fresh repo)
                        print("↑ Local branch has no remote counterpart.")
                        if backup:
                            result = dotfiles.push()
                            if result["success"]:
                                print("✓ Pushed to remote")
                            else:
                                print(f"✗ Push failed: {result['error']}")
                        else:
                            print("\nTo push, run: freckle run --backup")
                            return 0

            for manager in tool_managers:
                if manager.bin_name in enabled_modules:
                    manager.setup()
            
            print(f"\n--- {action_name} Complete! ---\n")
            
        except Exception as e:
            self.logger.error(f"Freckle failed: {e}")
            return 1
        return 0

    def add(self, *files):
        """Add files to be tracked in your dotfiles repository.
        
        Usage:
            freckle add .freckle.yaml
            freckle add .vimrc .bashrc
            freckle add .config/starship.toml
            freckle add ~/.config/nvim/init.lua
        
        Paths can be:
        - Relative to home (e.g., .config/nvim/init.lua)
        - Absolute paths (e.g., /home/user/.zshrc)
        - Relative to current directory (e.g., ../somefile)
        
        After adding, run 'freckle run --backup' to commit and push.
        """
        if not files:
            print("Usage: freckle add <file> [file2] [file3] ...")
            print("\nExamples:")
            print("  freckle add .freckle.yaml")
            print("  freckle add .vimrc .bashrc")
            print("  freckle add .config/starship.toml")
            print("  freckle add ~/.config/nvim/init.lua")
            return 1
        
        config_path = self.env.home / ".freckle.yaml"
        config = Config(config_path, env=self.env)
        
        repo_url = config.get("dotfiles.repo_url")
        if not repo_url:
            self.logger.error("Dotfiles not configured. Run 'freckle init' first.")
            return 1
        
        dotfiles_dir = Path(config.get("dotfiles.dir")).expanduser()
        if not dotfiles_dir.is_absolute():
            dotfiles_dir = self.env.home / dotfiles_dir
        branch = config.get("dotfiles.branch")
        
        if not dotfiles_dir.exists():
            self.logger.error("Dotfiles repository not found. Run 'freckle run' first.")
            return 1
        
        dotfiles = DotfilesManager(repo_url, dotfiles_dir, self.env.home, branch)
        
        # Convert user-provided paths to paths relative to home directory
        home_relative_files = []
        for f in files:
            path = Path(f).expanduser()
            
            # If it's a relative path, resolve it from cwd first
            if not path.is_absolute():
                path = Path.cwd() / path
            
            # Resolve to get canonical path (handles .., symlinks, etc.)
            path = path.resolve()
            
            # Check if it's under home directory
            try:
                relative = path.relative_to(self.env.home)
                home_relative_files.append(str(relative))
            except ValueError:
                # Path is not under home directory
                self.logger.error(f"File must be under home directory: {f}")
                continue
        
        if not home_relative_files:
            return 1
        
        result = dotfiles.add_files(home_relative_files)
        
        if result["added"]:
            print(f"✓ Staged {len(result['added'])} file(s) for tracking:")
            for f in result["added"]:
                print(f"    + {f}")
        
        if result["skipped"]:
            print(f"\n⚠ Skipped {len(result['skipped'])} file(s):")
            for f in result["skipped"]:
                file_path = self.env.home / f
                if not file_path.exists():
                    print(f"    - {f} (file not found)")
                else:
                    print(f"    - {f} (failed to add)")
        
        if result["added"]:
            print("\nTo commit and push, run: freckle run --backup")
            return 0
        else:
            return 1

    def status(self):
        """Show current setup status and check for updates."""
        config_path = self.env.home / ".freckle.yaml"
        config = Config(config_path, env=self.env)
        
        repo_url = config.get("dotfiles.repo_url")
        dotfiles_dir = Path(config.get("dotfiles.dir")).expanduser()
        if not dotfiles_dir.is_absolute():
            dotfiles_dir = self.env.home / dotfiles_dir
        branch = config.get("dotfiles.branch")
        
        print(f"\n--- freckle Status ---")
        print(f"OS     : {self.env.os_info['pretty_name']} ({self.env.os_info['machine']})")
        print(f"Kernel : {self.env.os_info['release']}")
        print(f"User   : {self.env.user}")
        
        pkg_mgr = SystemPackageManager(self.env)
        
        dotfiles = None
        if repo_url:
            dotfiles = DotfilesManager(repo_url, dotfiles_dir, self.env.home, branch)

        tool_managers = [
            ZshManager(self.env, pkg_mgr),
            TmuxManager(self.env, pkg_mgr),
            NvimManager(self.env, pkg_mgr)
        ]
        
        # Freckle config status
        print("\nConfiguration:")
        if config_path.exists():
            if dotfiles:
                status = dotfiles.get_file_sync_status(".freckle.yaml")
                status_str = {
                    "up-to-date": "✓ up-to-date",
                    "modified": "⚠ modified locally",
                    "behind": "↓ update available (behind remote)",
                    "untracked": "✗ not tracked in dotfiles",
                    "missing": "✓ local only",
                    "not-found": "✓ local only",
                    "error": "⚠ error checking status"
                }.get(status, f"status: {status}")
                print(f"  .freckle.yaml : {status_str}")
            else:
                print(f"  .freckle.yaml : ✓ exists (dotfiles not configured)")
        else:
            print(f"  .freckle.yaml : ✗ not found (run 'freckle init')")

        # Collect all config files associated with tool managers
        tool_config_files = set()
        
        print("\nCore Tools:")
        for manager in tool_managers:
            info = pkg_mgr.get_binary_info(manager.bin_name)
            if info["found"]:
                print(f"  {manager.name}:")
                print(f"    Binary : {info['path']} ({info['version']})")
            else:
                print(f"  {manager.name}: ✗ not found in PATH")
                continue

            if dotfiles:
                for cfg in manager.config_files:
                    tool_config_files.add(cfg)
                    status = dotfiles.get_file_sync_status(cfg)
                    if status == "not-found":
                        continue
                        
                    status_str = {
                        "up-to-date": "✓ up-to-date",
                        "modified": "⚠ modified locally",
                        "behind": "↓ update available (behind remote)",
                        "untracked": "✗ not tracked",
                        "missing": "✗ missing from home",
                        "error": "⚠ error checking status"
                    }.get(status, f"status: {status}")
                    
                    print(f"    Config : {status_str} ({cfg})")
        
        # Show all other tracked files (not associated with a tool manager)
        if dotfiles:
            all_tracked = dotfiles.get_tracked_files()
            # Exclude .freckle.yaml (shown in Configuration) and tool config files
            other_tracked = [
                f for f in all_tracked 
                if f != ".freckle.yaml" and f not in tool_config_files
            ]
            
            if other_tracked:
                print("\nOther Tracked Files:")
                for f in sorted(other_tracked):
                    status = dotfiles.get_file_sync_status(f)
                    status_str = {
                        "up-to-date": "✓",
                        "modified": "⚠ modified",
                        "behind": "↓ behind",
                        "missing": "✗ missing",
                        "error": "?"
                    }.get(status, "?")
                    print(f"  {status_str} {f}")
            
        # Global Dotfiles Status
        if not repo_url:
            print("\nDotfiles: Not configured (run 'freckle init')")
        else:
            print(f"\nDotfiles ({repo_url}):")
            try:
                report = dotfiles.get_detailed_status()
                if not report["initialized"]:
                    print("  Status: Not initialized")
                else:
                    branch_info = report.get('branch_info', {})
                    effective_branch = report.get('branch', branch)
                    
                    # Show branch with context if there's a mismatch
                    reason = branch_info.get('reason', 'exact')
                    if reason == 'exact':
                        print(f"  Branch: {effective_branch}")
                    elif reason == 'main_master_swap':
                        print(f"  Branch: {effective_branch}")
                        print(f"    Note: '{branch_info.get('configured')}' not found, using '{effective_branch}'")
                    elif reason == 'not_found':
                        print(f"  Branch: {effective_branch} (configured, but not found!)")
                        available = branch_info.get('available', [])
                        if available:
                            print(f"    Available branches: {', '.join(available)}")
                        else:
                            print(f"    No branches found - is this repo initialized?")
                    else:
                        # fallback_head or fallback_default
                        print(f"  Branch: {effective_branch}")
                        if branch_info.get('message'):
                            print(f"    Note: {branch_info['message']}")
                    
                    print(f"  Local Commit : {report['local_commit']}")
                    
                    if report.get("remote_branch_missing"):
                        print(f"  Remote Commit: ✗ No origin/{effective_branch} branch!")
                        print(f"    The local '{effective_branch}' branch has no remote counterpart.")
                        print(f"    To push it: git --git-dir=~/.dotfiles push -u origin {effective_branch}")
                    else:
                        print(f"  Remote Commit: {report.get('remote_commit', 'N/A')}")
                    
                    if report.get("fetch_failed"):
                        print("  Remote Status: ⚠ Could not fetch (offline?)")
                    
                    if report["has_local_changes"]:
                        print("  Local Changes: Yes (uncommitted changes in your home directory)")
                    else:
                        print("  Local Changes: No")
                    
                    if report.get("remote_branch_missing"):
                        pass  # Already explained above
                    elif report.get("is_ahead"):
                        print(f"  Ahead: Yes ({report.get('ahead_count', 0)} commits not pushed)")
                        
                    if report.get("is_behind"):
                        print(f"  Behind: Yes ({report.get('behind_count', 0)} commits to pull)")
                    elif not report.get("fetch_failed") and not report.get("remote_branch_missing"):
                        print("  Behind: No (up to date)")
                        
            except Exception as e:
                print(f"  Error checking status: {e}")
        print("")

    def version(self):
        """Show the version of freckle."""
        print(f"freckle version {get_version()}")


def main():
    """Main entry point for the freckle CLI."""
    fire.Fire(FreckleCLI)
