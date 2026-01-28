# freckle

Keep track of all your dot(file)s.

A dotfiles manager with tool installation for Linux and macOS.

## Overview

Freckle automates the "bare repo" strategy for dotfiles with intelligent
conflict resolution, automatic backups, and cross-platform package management.

## Features

- **Interactive Setup**: Run `freckle init` to configure your repository.
- **Bare Repo Management**: Safely check out dotfiles into your home
  directory, backing up conflicts automatically.
- **Profile Support**: Manage multiple machine configurations via git branches.
- **Secret Detection**: Blocks accidental commits of private keys and tokens.
- **Restore Points**: Automatic backups before destructive operations.
- **Declarative Tools**: Define tools in config with automatic package manager
  selection (brew, apt, cargo, pip, npm) and curated script support.
- **Platform Aware**: Supports Debian-based Linux (`apt`) and macOS (`brew`).
- **Scheduled Saves**: Automatic daily/weekly saves via launchd or cron.
- **Health Checks**: `freckle doctor` diagnoses common issues.

## Installation

### Quick Install (Recommended)

Bootstrap freckle on a fresh system with a single command:

```bash
curl -LsSf https://raw.githubusercontent.com/peterprescott/freckle/main/scripts/bootstrap.sh | bash
```

This installs [uv](https://docs.astral.sh/uv/) and freckle automatically.

### Manual Install

If you already have uv:

```bash
uv tool install freckle
```

Or with pip:

```bash
pip install freckle
```

## Quick Start

```bash
# Initialize (interactive setup - clones existing or creates new repo)
freckle init

# Check status of dotfiles
freckle status

# Save local changes
freckle save

# Fetch remote changes
freckle fetch

# Run health checks
freckle doctor
```

## Commands

### Core Commands

```bash
freckle init              # Interactive setup wizard (clones or creates repo)
freckle status            # Show detailed status of dotfiles and tools
freckle save              # Save local changes (works offline)
freckle fetch             # Fetch and apply remote changes
freckle doctor            # Run health checks and diagnostics
```

### File Management

```bash
freckle track <file>      # Start tracking a file (auto-saves)
freckle untrack <file>    # Stop tracking a file (auto-saves)
freckle config            # Open config file in your editor
freckle config open nvim  # Open a tool's config files
```

Secret detection is built-in. Tracking private keys or tokens will be blocked:

```bash
$ freckle track .ssh/id_rsa
✗ Blocked: .ssh/id_rsa appears to contain a private key.
  To override: freckle track --force .ssh/id_rsa
```

### Profile Management

Profiles let you maintain different configurations for different machines.
Each profile corresponds to a git branch (profile name = branch name):

```bash
freckle profile list              # List all profiles
freckle profile show              # Show current profile details
freckle profile switch <name>     # Switch to a profile
freckle profile create <name>     # Create a new profile
freckle profile delete <name>     # Delete a profile
```

Create profiles with inheritance to reduce duplication:

```bash
# Create profile inheriting from 'main' with additional modules
freckle profile create mac --include main --modules karabiner,homebrew

# Create server profile excluding desktop tools
freckle profile create server --include main --exclude nvim,tmux --modules docker
```

Keep configuration in sync across profiles:

```bash
freckle config check              # Check config consistency
freckle config propagate          # Sync config to all branches
```

### Tool Management

Tools are defined in your config and installed via the best available
package manager:

```bash
freckle tools                     # Show tool installation status
freckle tools install <name>      # Install a specific tool
```

### History & Restore

View the history of your dotfiles and restore from any point:

```bash
freckle history                   # Show recent commits
freckle history nvim              # History for specific tool
freckle history ~/.zshrc          # History for specific file
freckle history --oneline         # Compact format

freckle restore --list            # List backup restore points
freckle restore <commit> nvim     # Restore tool from git commit
freckle restore <commit> --all    # Restore all files from commit
freckle restore <commit> --dry-run  # Preview before restoring
```

### Comparing Changes

```bash
freckle changes                   # Show uncommitted local changes
freckle diff abc123 def456 nvim   # Compare tool between commits
```

### Scheduled Saves

```bash
freckle schedule          # Show current schedule status
freckle schedule daily    # Enable daily saves at 9am
freckle schedule weekly   # Enable weekly saves (Sundays)
freckle schedule off      # Disable scheduled saves
```

## Shell Completion

Freckle supports tab completion for bash, zsh, and fish.

```bash
# Install completion for your current shell
freckle --install-completion

# Or show the completion script to customize installation
freckle --show-completion
```

After installation, restart your shell or source your shell config.

## Global Options

```bash
freckle --verbose ...     # Enable debug logging
freckle save --dry-run    # See what would be saved
freckle fetch --dry-run   # Preview what would change
```

## Configuration

Freckle stores its configuration in `~/.freckle.yaml` (or `~/.freckle.yml`).

### Example

```yaml
dotfiles:
  repo_url: "https://github.com/{local_user}/dotfiles.git"
  dir: "~/.dotfiles"

profiles:
  # Base profile - common tools for all machines
  # Profile name = git branch name (e.g., 'main' branch)
  main:
    description: "Base configuration"
    modules:
      - git
      - zsh
      - tmux
      - nvim

  # macOS profile inherits everything from main, adds mac-specific tools
  mac:
    description: "macOS workstation"
    include: [main]
    modules:
      - karabiner
      - homebrew

  # Linux profile inherits from main, adds linux-specific tools
  linux:
    description: "Linux workstation"
    include: [main]
    modules:
      - keyd

  # Server profile inherits from main but excludes desktop tools
  server:
    description: "Headless server"
    include: [main]
    exclude: [nvim, tmux]
    modules:
      - docker

tools:
  git:
    brew: git
    apt: git
    config_files:
      - ~/.gitconfig
  zsh:
    brew: zsh
    apt: zsh
    config_files:
      - ~/.zshrc
  nvim:
    brew: neovim
    apt: neovim
    config_files:
      - ~/.config/nvim/
  docker:
    brew: docker
    apt: docker.io
  karabiner:
    brew: karabiner-elements
    config_files:
      - ~/.config/karabiner/
  keyd:
    apt: keyd
    config_files:
      - /etc/keyd/
```

### Profile Inheritance

Profiles can inherit modules from other profiles using `include`, and exclude
specific modules using `exclude`:

- **`include`**: List of profiles to inherit modules from
- **`exclude`**: List of modules to remove from inherited set
- **`modules`**: Additional modules specific to this profile

Resolution: `(inherited - excluded) ∪ own_modules`

```yaml
profiles:
  main:
    modules: [git, zsh, nvim, tmux]

  server:
    include: [main]
    exclude: [nvim, tmux]
    modules: [docker]
    # Resolved: {git, zsh, docker}
```

### Variables

- `{local_user}`: Automatically replaced with your system username.
- Custom variables: Define your own in the `vars` section.

```yaml
vars:
  git_host: "github.com"

dotfiles:
  repo_url: "https://{git_host}/{local_user}/dotfiles.git"
```

## License

MIT
