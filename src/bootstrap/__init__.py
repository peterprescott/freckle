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

        pkg_mgr = PackageManager(self.env)

        try:
            if "dotfiles" in enabled_modules:
                dotfiles = DotfilesManager(
                    repo_url=repo_url,
                    dotfiles_dir=dotfiles_dir,
                    work_tree=work_tree,
                    branch=branch
                )
                dotfiles.setup()
                self.logger.info("Dotfiles setup complete!")

            if "zsh" in enabled_modules:
                zsh = ZshManager(self.env, pkg_mgr)
                zsh.setup()

            if "tmux" in enabled_modules:
                tmux = TmuxManager(self.env, pkg_mgr)
                tmux.setup()

            if "nvim" in enabled_modules:
                nvim = NvimManager(self.env, pkg_mgr)
                nvim.setup()
            
            self.logger.info("Bootstrap sequence complete!")
            
        except Exception as e:
            self.logger.error(f"Bootstrap failed: {e}")
            return 1
        return 0

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
    elif sys.argv[1] not in ["run", "init", "version"] and not sys.argv[1].startswith("-"):
        # If the first argument is not a command or a flag, it might be a flag for 'run'
        # e.g., 'bootstrap --repo ...'
        sys.argv.insert(1, "run")
        
    fire.Fire(BootstrapCLI)

if __name__ == "__main__":
    main()
