#!/bin/bash
set -e

# Freckle Docker E2E Runner
# This script builds and runs freckle in a clean Debian container.

# Build the image
echo "Building Docker E2E image..."
docker build -t freckle-e2e -f tests/e2e/Dockerfile .

# Run the container and execute freckle
echo "Running E2E test in container..."
docker run --rm freckle-e2e /bin/bash -c "
    echo '--- Running freckle run ---'
    cd ~/freckle && freckle run
    echo '--- Verifying state ---'
    [ -f ~/.zshrc ] && echo '✓ .zshrc exists' || (echo '✗ .zshrc missing' && exit 1)
    [ -f ~/.tmux.conf ] && echo '✓ .tmux.conf exists' || (echo '✗ .tmux.conf missing' && exit 1)
    [ -d ~/.local/share/nvim/lazy/lazy.nvim ] && echo '✓ lazy.nvim installed' || (echo '✗ lazy.nvim missing' && exit 1)
    echo 'E2E Success!'
"
