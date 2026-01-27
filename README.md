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
- **Scheduled Backups**: Automatic daily/weekly backups via launchd or cron.
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
# Initialize (interactive setup)
freckle init

# Check status of dotfiles
freckle sync

# Commit and push local changes
freckle backup

# Pull remote changes
freckle update

# Run health checks
freckle doctor
```

## Commands

### Core Commands

```bash
freckle init              # Interactive setup wizard
freckle sync              # Check dotfiles status, clone on first run
freckle backup            # Commit and push local changes
freckle update            # Pull and apply remote changes
freckle status            # Show detailed status of dotfiles and tools
freckle doctor            # Run health checks and diagnostics
```

### File Management

```bash
freckle add <file>        # Track a new file in dotfiles
freckle remove <file>     # Stop tracking a file
freckle config            # Open config file in your editor
```

Secret detection is built-in. Adding private keys or tokens will be blocked:

```bash
$ freckle add .ssh/id_rsa
✗ Blocked: .ssh/id_rsa appears to contain a private key.
  To override: freckle add --force .ssh/id_rsa
```

### Profile Management

Profiles let you maintain different configurations for different machines.
Each profile is a git branch:

```bash
freckle profile list              # List all profiles
freckle profile switch <name>     # Switch to a profile
freckle profile create <name>     # Create a new profile
freckle profile delete <name>     # Delete a profile
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

### Backup & Restore

Freckle creates restore points before destructive operations:

```bash
freckle restore --list            # List available restore points
freckle restore <timestamp>       # Restore from a specific point
```

### Git Convenience

```bash
freckle log               # Show commit history
freckle diff              # Show uncommitted changes
```

### Scheduled Backups

```bash
freckle schedule          # Show current schedule status
freckle schedule daily    # Enable daily backups at 9am
freckle schedule weekly   # Enable weekly backups (Sundays)
freckle schedule off      # Disable scheduled backups
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
freckle sync --dry-run    # Preview what would happen
freckle backup --dry-run  # See what would be committed
```

## Configuration

Freckle stores its configuration in `~/.freckle.yaml`.

### Example

```yaml
dotfiles:
  repo_url: "https://github.com/{local_user}/dotfiles.git"
  branch: "main"
  dir: "~/.dotfiles"

profiles:
  default:
    tools:
      - git
      - zsh
      - tmux
      - nvim

  work:
    tools:
      - git
      - zsh
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
