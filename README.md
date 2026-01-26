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
- **Tool Installation**: Automated setup for Zsh, Tmux, and Neovim
  (with `lazy.nvim` bootstrapping).
- **Platform Aware**: Supports Debian-based Linux (`apt`) and macOS (`brew`).
- **Scheduled Backups**: Automatic daily/weekly backups via launchd or cron.
- **Flexible Templating**: Use `{local_user}` or custom variables in config.

## Installation

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
```

## Commands

### Core Commands

```bash
freckle init              # Interactive setup wizard
freckle sync              # Check dotfiles status, clone on first run
freckle backup            # Commit and push local changes
freckle update            # Pull and apply remote changes
freckle status            # Show detailed status of dotfiles and tools
```

### File Management

```bash
freckle add <file>        # Track a new file in dotfiles
freckle remove <file>     # Stop tracking a file
freckle config            # Open config file in your editor
```

### Tool Management

```bash
freckle tools             # Show installation status of tools
freckle tools --install   # Install missing tools and run setup
freckle tools nvim -i     # Install/setup a specific tool
```

### Git Convenience

```bash
freckle log               # Show commit history
freckle branch            # List/switch/create branches
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

### Variables

- `{local_user}`: Automatically replaced with your system username.
- Custom variables: Define your own in the `vars` section.

### Example

```yaml
vars:
  git_user: "yourusername"
  git_host: "github.com"

dotfiles:
  repo_url: "https://{git_host}/{git_user}/dotfiles.git"
  branch: "main"
  dir: "~/.dotfiles"

modules:
  - dotfiles
  - zsh
  - tmux
  - nvim
```

## License

MIT
