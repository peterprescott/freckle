# bootstrap

A robust, multi-platform system bootstrapper designed to manage dotfiles and core tools (Zsh, Tmux, Neovim) across Linux and macOS.

## Overview

This tool automates the "bare repo" strategy for dotfiles with intelligent conflict resolution, automatic backups, and cross-platform package management.

## Features
- **Interactive Setup**: Run `bootstrap init` to configure your repository.
- **Bare Repo Management**: Safely check out dotfiles into your home directory, backing up conflicts automatically.
- **Core Trio Support**: Automated setup for Zsh (default shell), Tmux, and Neovim (with `lazy.nvim` bootstrapping).
- **Platform Aware**: Supports Debian-based Linux (`apt`) and macOS (`homebrew`).
- **Flexible Templating**: Use `{local_user}` or custom variables in your configuration.

## Installation

```bash
uv pip install .
```

## Usage

### 1. Initialize
First-time users should run the initialization command to set up their dotfiles repository:

```bash
bootstrap init
```
This will create a `~/.bootstrap.yaml` file with your settings.

### 2. Run
Execute the bootstrap sequence:

```bash
bootstrap run
```

## Configuration (`~/.bootstrap.yaml`)

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
  repo_url: "https://{git_host}/{git_user}/.dotfiles.git"
  branch: "master"
  dir: "/home/{local_user}/.dotfiles"

modules:
  - dotfiles
  - zsh
  - tmux
  - nvim
```
