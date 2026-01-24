import logging
import sys
import yaml
import fire
from pathlib import Path
from .environment import Environment
from .dotfiles import DotfilesManager
from .nvim import NvimManager
from .zsh import ZshManager
from .tmux import TmuxManager
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

    def run(self, repo=None, branch=None):
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
        print(f"Platform: {self.env.os.value}")
        
        pkg_mgr = PackageManager(self.env)

        try:
            if "dotfiles" in enabled_modules:
                print(f"[*] {action_name}ing dotfiles from {repo_url}...")
                dotfiles = DotfilesManager(
                    repo_url=repo_url,
                    dotfiles_dir=dotfiles_dir,
                    work_tree=work_tree,
                    branch=branch
                )
                dotfiles.setup()
                self.logger.info("Dotfiles setup complete!")

            if "zsh" in enabled_modules:
                print("[*] Configuring Zsh...")
                zsh = ZshManager(self.env, pkg_mgr)
                zsh.setup()

            if "tmux" in enabled_modules:
                print("[*] Configuring Tmux...")
                tmux = TmuxManager(self.env, pkg_mgr)
                tmux.setup()

            if "nvim" in enabled_modules:
                print("[*] Configuring Neovim...")
                nvim = NvimManager(self.env, pkg_mgr)
                nvim.setup()
            
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
        print(f"OS: {self.env.os.value}")
        print(f"User: {self.env.user}")
        
        pkg_mgr = PackageManager(self.env)
        dotfiles = None
        if repo_url:
            dotfiles = DotfilesManager(repo_url, dotfiles_dir, self.env.home, branch)

        # Core Tools Status
        tools = {
            "zsh": [".zshrc"],
            "tmux": [".tmux.conf"],
            "nvim": [".config/nvim/init.lua", ".config/nvim/init.vim"]
        }
        
        print("\nCore Tools:")
        for tool, configs in tools.items():
            info = pkg_mgr.get_binary_info(tool)
            if info["found"]:
                print(f"  {tool}:")
                print(f"    Binary : {info['path']} ({info['version']})")
            else:
                print(f"  {tool}: ✗ not found in PATH")
                continue

            if dotfiles:
                for cfg in configs:
                    status = dotfiles.get_file_sync_status(cfg)
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
                report = dotfiles.get_status()
                if not report["installed"]:
                    print("  Status: Not initialized")
                else:
                    print(f"  Branch: {branch}")
                    print(f"  Local Commit : {report['local_commit']}")
                    print(f"  Remote Commit: {report['remote_commit']}")
                    
                    if report["local_changes"]:
                        print("  Local Changes: Yes (uncommitted changes in your home directory)")
                    else:
                        print("  Local Changes: No")
                        
                    if report["behind"]:
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
