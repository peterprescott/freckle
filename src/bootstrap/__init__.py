import logging
import sys
import yaml
import fire
from pathlib import Path
from .environment import Environment
from .dotfiles import DotfilesManager
from .managers.nvim import NvimManager
from .managers.zsh import ZshManager
from .managers.tmux import TmuxManager
from .config import Config
from .packages import PackageManager

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )

class BootstrapCLI:
    def __init__(self):
        setup_logging()
        self.env = Environment()
        self.logger = logging.getLogger(__name__)

    def init(self, force=False):
        """Initialize configuration"""
        config_path = self.env.home / ".bootstrap.yaml"
        
        if config_path.exists() and not force:
            self.logger.error(f"Config file already exists at {config_path}. Use --force to overwrite.")
            return 1

        print("--- bootstrap Initialization ---")
        repo_url = input("Enter your dotfiles repository URL: ").strip()
        branch = input("Enter your preferred branch (default: main): ").strip() or "main"
        dotfiles_dir = input("Enter directory for bare repo (default: ~/.dotfiles): ").strip() or "~/.dotfiles"

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
        print("\nInitialization complete! You can now run 'bootstrap run'.")
        return 0

    def run(self, repo=None, branch=None, backup=False, update=False):
        """Run the bootstrap sequence"""
        config_path = self.env.home / ".bootstrap.yaml"
        config = Config(config_path, env=self.env)
        
        # Override from CLI
        if repo:
            config.data["dotfiles"]["repo_url"] = repo
        if branch:
            config.data["dotfiles"]["branch"] = branch

        repo_url = config.get("dotfiles.repo_url")
        if not repo_url:
            self.logger.error("No dotfiles repository URL found. Run 'bootstrap init' first or use --repo.")
            return 1

        dotfiles_dir = Path(config.get("dotfiles.dir")).expanduser()
        branch = config.get("dotfiles.branch")
        work_tree = self.env.home
        enabled_modules = config.get("modules", [])

        is_first_run = not dotfiles_dir.exists()
        action_name = "Setup" if is_first_run else "Sync"
        
        print(f"\n--- bootstrap {action_name} ---")
        print(f"Platform: {self.env.os_info['pretty_name']}")
        
        pkg_mgr = PackageManager(self.env)
        
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
                    local = report["has_local_changes"]
                    remote = report["has_remote_changes"]

                    if not local and not remote:
                        print("✓ Dotfiles are up-to-date.")
                    elif local and not remote:
                        # Option B: Local change, no remote change
                        print("⚠ You have local changes that are not backed up:")
                        for f in report["changed_files"]:
                            print(f"    - {f}")
                        
                        if backup:
                            msg = f"Automated backup from {self.env.os_info['pretty_name']}"
                            dotfiles.commit_and_push(msg)
                        else:
                            print("\nTo backup these changes, run: bootstrap run --backup")
                            return 0 # Stop dotfiles sync but continue with others? 
                                     # Actually user said "just stop", let's return.
                    elif not local and remote:
                        # Option C: Remote change, no local change
                        print(f"↓ Remote repository ({branch}) has new updates.")
                        if update:
                            dotfiles.force_checkout()
                        else:
                            print("\nTo update your local files, run: bootstrap run --update")
                            return 0
                    elif local and remote:
                        # Option D: Conflict
                        print("‼ CONFLICT: Both local and remote have new (different) changes.")
                        print(f"  Local Commit : {report['local_commit']}")
                        print(f"  Remote Commit: {report['remote_commit']}")
                        
                        print("\nLocal changes:")
                        for f in report["changed_files"]:
                            print(f"    - {f}")
                            
                        if backup:
                            msg = "Manual backup during conflict"
                            dotfiles.commit_and_push(msg)
                        elif update:
                            dotfiles.force_checkout()
                        else:
                            print("\nOptions to resolve conflict:")
                            print("  - To keep local changes and backup: bootstrap run --backup")
                            print("  - To discard local changes and update: bootstrap run --update")
                            return 0

            for manager in tool_managers:
                if manager.bin_name in enabled_modules:
                    manager.setup()
            
            print(f"\n--- {action_name} Complete! ---\n")
            
        except Exception as e:
            self.logger.error(f"Bootstrap failed: {e}")
            return 1
        return 0

    def status(self):
        """Show current setup status and check for updates"""
        config_path = self.env.home / ".bootstrap.yaml"
        config = Config(config_path, env=self.env)
        
        repo_url = config.get("dotfiles.repo_url")
        dotfiles_dir = Path(config.get("dotfiles.dir")).expanduser()
        branch = config.get("dotfiles.branch")
        
        print(f"\n--- bootstrap Status ---")
        print(f"OS   : {self.env.os_info['pretty_name']} ({self.env.os_info['machine']})")
        print(f"Kernel : {self.env.os_info['release']}")
        print(f"User   : {self.env.user}")
        
        pkg_mgr = PackageManager(self.env)
        
        dotfiles = None
        if repo_url:
            dotfiles = DotfilesManager(repo_url, dotfiles_dir, self.env.home, branch)

        tool_managers = [
            ZshManager(self.env, pkg_mgr),
            TmuxManager(self.env, pkg_mgr),
            NvimManager(self.env, pkg_mgr)
        ]
        
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
            
        # Global Dotfiles Status
        if not repo_url:
            print("\nDotfiles: Not configured (run 'bootstrap init')")
        else:
            print(f"\nDotfiles ({repo_url}):")
            try:
                report = dotfiles.get_detailed_status()
                if not report["initialized"]:
                    print("  Status: Not initialized")
                else:
                    print(f"  Branch: {branch}")
                    print(f"  Local Commit : {report['local_commit']}")
                    print(f"  Remote Commit: {report['remote_commit']}")
                    
                    if report["has_local_changes"]:
                        print("  Local Changes: Yes (uncommitted changes in your home directory)")
                    else:
                        print("  Local Changes: No")
                        
                    if report["has_remote_changes"]:
                        print("  Update Available: Yes (remote has new commits)")
                    else:
                        print("  Update Available: No (up to date)")
            except Exception as e:
                print(f"  Error checking status: {e}")
        print("")

    def version(self):
        """Show the version of the bootstrap tool"""
        import importlib.metadata
        try:
            version = importlib.metadata.version("bootstrap")
            print(f"bootstrap version {version}")
        except importlib.metadata.PackageNotFoundError:
            # Fallback for development if not installed
            print("bootstrap version (development)")

def main():
    # Handle version flags before Fire takes over
    if len(sys.argv) > 1 and sys.argv[1] in ["--version", "-v", "version"]:
        # If it's the 'version' command, Fire would handle it, 
        # but we handle it here for consistency with flags.
        # However, for 'version' we can just let Fire handle it if we want.
        # Let's handle flags specifically.
        if sys.argv[1] in ["--version", "-v"]:
            import importlib.metadata
            try:
                version = importlib.metadata.version("bootstrap")
                print(f"bootstrap version {version}")
            except importlib.metadata.PackageNotFoundError:
                print("bootstrap version (development)")
            return

    # If no command is provided, default to 'run'
    if len(sys.argv) == 1:
        sys.argv.append("run")
    elif sys.argv[1] not in ["run", "init", "version", "status"] and not sys.argv[1].startswith("-"):
        # If the first argument is not a command or a flag, it might be a flag for 'run'
        # e.g., 'bootstrap --repo ...'
        sys.argv.insert(1, "run")
        
    fire.Fire(BootstrapCLI)

if __name__ == "__main__":
    main()
