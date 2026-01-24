# bootstrap

A robust, multi-platform system bootstrapper designed to handle the configuration challenges of a hybrid Linux (Debian/i3/XFCE) and macOS environment.

## Overview

This project is the successor to a collection of shell-based bootstrapping scripts. It aims to provide:
- **Idempotency**: Safely run multiple times without corrupting configurations.
- **Robust Dotfiles Management**: Automates the "bare repo" strategy with intelligent conflict resolution and backups.
- **Platform Awareness**: Seamlessly handles differences between `apt` and `homebrew`.
- **Modular Design**: Easy to add new configuration modules for specific tools (nvim, tmux, zsh, etc.).

## Installation

```bash
uv pip install .
```

## Usage

```bash
bootstrap
```
