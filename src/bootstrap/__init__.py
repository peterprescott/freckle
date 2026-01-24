import logging
import sys
import argparse
import yaml
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

def cmd_init(args, env: Environment):
    logger = logging.getLogger(__name__)
    config_path = env.home / ".bootstrap.yaml"
    
    if config_path.exists() and not args.force:
        logger.error(f"Config file already exists at {config_path}. Use --force to overwrite.")
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
    
    logger.info(f"Created configuration at {config_path}")
    print("\nInitialization complete! You can now run 'bootstrap run'.")
    return 0

def cmd_run(args, env: Environment):
    logger = logging.getLogger(__name__)
    config_path = env.home / ".bootstrap.yaml"
    config = Config(config_path, env=env)
    
    # Override from CLI
    if args.repo:
        config.data["dotfiles"]["repo_url"] = args.repo
    if args.branch:
        config.data["dotfiles"]["branch"] = args.branch

    repo_url = config.get("dotfiles.repo_url")
    if not repo_url:
        logger.error("No dotfiles repository URL found. Run 'bootstrap init' first or use --repo.")
        return 1

    dotfiles_dir = Path(config.get("dotfiles.dir")).expanduser()
    branch = config.get("dotfiles.branch")
    work_tree = env.home
    enabled_modules = config.get("modules", [])

    pkg_mgr = PackageManager(env)

    try:
        if "dotfiles" in enabled_modules:
            dotfiles = DotfilesManager(
                repo_url=repo_url,
                dotfiles_dir=dotfiles_dir,
                work_tree=work_tree,
                branch=branch
            )
            dotfiles.setup()
            logger.info("Dotfiles setup complete!")

        if "zsh" in enabled_modules:
            zsh = ZshManager(env, pkg_mgr)
            zsh.setup()

        if "tmux" in enabled_modules:
            tmux = TmuxManager(env, pkg_mgr)
            tmux.setup()

        if "nvim" in enabled_modules:
            nvim = NvimManager(env, pkg_mgr)
            nvim.setup()
        
        logger.info("Bootstrap sequence complete!")
        
    except Exception as e:
        logger.error(f"Bootstrap failed: {e}")
        return 1
    return 0

def main() -> None:
    setup_logging()
    env = Environment()
    
    parser = argparse.ArgumentParser(description="AnyMachine Bootstrap Tool")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # init command
    init_parser = subparsers.add_parser("init", help="Initialize configuration")
    init_parser.add_argument("--force", action="store_true", help="Overwrite existing config")

    # run command
    run_parser = subparsers.add_parser("run", help="Run the bootstrap sequence")
    run_parser.add_argument("--repo", help="Override dotfiles repository URL")
    run_parser.add_argument("--branch", help="Override dotfiles branch")

    args = parser.parse_args()

    if args.command == "init":
        sys.exit(cmd_init(args, env))
    elif args.command == "run" or args.command is None:
        if args.command is None:
            # Default behavior if no command is provided, for backward compatibility
            # but we'll transition to requiring 'run'
            pass
        sys.exit(cmd_run(args, env))
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()
