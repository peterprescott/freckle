# freckle

Keep track of all your dot(file)s.

A dotfiles manager with tool installation for Linux and macOS.

## Overview

Freckle automates the "bare repo" strategy for dotfiles with intelligent conflict resolution, automatic backups, and cross-platform package management.

## Features
- **Interactive Setup**: Run `freckle init` to configure your repository.
- **Bare Repo Management**: Safely check out dotfiles into your home directory, backing up conflicts automatically.
- **Core Trio Support**: Automated setup for Zsh (default shell), Tmux, and Neovim (with `lazy.nvim` bootstrapping).
- **Platform Aware**: Supports Debian-based Linux (`apt`) and macOS (`homebrew`).
- **Flexible Templating**: Use `{local_user}` or custom variables in your configuration.

## Installation

```bash
uv tool install freckle
```

Or install from source:

```bash
uv pip install .
```

## Usage

### 1. Initialize
First-time users should run the initialization command to set up their dotfiles repository:

```bash
freckle init
```
This will create a `~/.freckle.yaml` file with your settings.

### 2. Run
Execute the sync sequence:

```bash
freckle run
```

### 3. Check Status
See the current state of your dotfiles and tools:

```bash
freckle status
```

### 4. Add Files
Track new files in your dotfiles repository:

```bash
freckle add .vimrc
freckle run --backup
```

## Configuration (`~/.freckle.yaml`)

You can customize the tool's behavior in your configuration file. 

### Variables
- `{local_user}`: Automatically replaced with your system username.
- Custom variables: Define your own in the `vars` section.

### Example
```yaml
vars:
  git_user: "peterprescott"
  git_host: "github.com"

dotfiles:
  repo_url: "https://{git_host}/{git_user}/dotfiles.git"
  branch: "main"
  dir: "/home/{local_user}/.dotfiles"

modules:
  - dotfiles
  - zsh
  - tmux
  - nvim
```
