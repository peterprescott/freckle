import logging
import sys
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

def main() -> None:
    setup_logging()
    logger = logging.getLogger(__name__)
    
    logger.info("Starting AnyMachine Bootstrap...")
    
    env = Environment()
    logger.info(f"Detected Environment: {env}")

    # Load Configuration
    config_path = env.home / ".bootstrap.yaml"
    config = Config(config_path)
    if config_path.exists():
        logger.info(f"Loaded config from {config_path}")
    else:
        logger.info("Using default configuration (no .bootstrap.yaml found)")

    pkg_mgr = PackageManager(env)

    # Dotfiles Configuration
    repo_url = config.get("dotfiles.repo_url")
    dotfiles_dir = Path(config.get("dotfiles.dir")).expanduser()
    branch = config.get("dotfiles.branch")
    work_tree = env.home

    try:
        dotfiles = DotfilesManager(
            repo_url=repo_url,
            dotfiles_dir=dotfiles_dir,
            work_tree=work_tree,
            branch=branch
        )
        dotfiles.setup()
        logger.info("Dotfiles setup complete!")

        # Core trio setup
        zsh = ZshManager(env, pkg_mgr)
        zsh.setup()

        tmux = TmuxManager(env, pkg_mgr)
        tmux.setup()

        nvim = NvimManager(env, pkg_mgr)
        nvim.setup()
        
        logger.info("Core Trio setup complete!")
        
    except Exception as e:
        logger.error(f"Bootstrap failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
