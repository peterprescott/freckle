#!/bin/bash
# Freckle Bootstrap Script
# Usage: curl -LsSf https://raw.githubusercontent.com/peterprescott/freckle/main/scripts/bootstrap.sh | bash
#
# This script installs:
#   1. uv (Python package manager)
#   2. freckle (dotfiles manager)
#
# Requirements: curl, git, bash

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

info() {
    echo -e "${BLUE}==>${NC} $1"
}

success() {
    echo -e "${GREEN}✓${NC} $1"
}

warn() {
    echo -e "${YELLOW}!${NC} $1"
}

error() {
    echo -e "${RED}✗${NC} $1"
    exit 1
}

# Check for required commands
check_requirements() {
    info "Checking requirements..."
    
    if ! command -v curl &> /dev/null; then
        error "curl is required but not installed."
    fi
    success "curl found"
    
    if ! command -v git &> /dev/null; then
        error "git is required but not installed."
    fi
    success "git found"
}

# Detect shell and config file
detect_shell_config() {
    case "$SHELL" in
        */zsh)
            echo "$HOME/.zshrc"
            ;;
        */bash)
            if [[ -f "$HOME/.bash_profile" ]]; then
                echo "$HOME/.bash_profile"
            else
                echo "$HOME/.bashrc"
            fi
            ;;
        */fish)
            echo "$HOME/.config/fish/config.fish"
            ;;
        *)
            echo "$HOME/.profile"
            ;;
    esac
}

# Install uv
install_uv() {
    if command -v uv &> /dev/null; then
        success "uv is already installed ($(uv --version))"
        return 0
    fi
    
    info "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    
    # Add uv to PATH for this session
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
    
    if command -v uv &> /dev/null; then
        success "uv installed ($(uv --version))"
    else
        error "uv installation failed. Please check the output above."
    fi
}

# Install freckle
install_freckle() {
    if command -v freckle &> /dev/null; then
        success "freckle is already installed ($(freckle --version 2>/dev/null || echo 'version unknown'))"
        return 0
    fi
    
    info "Installing freckle..."
    uv tool install freckle
    
    # uv tools are installed to ~/.local/bin
    export PATH="$HOME/.local/bin:$PATH"
    
    if command -v freckle &> /dev/null; then
        success "freckle installed"
    else
        error "freckle installation failed. Please check the output above."
    fi
}

# Print next steps
print_next_steps() {
    local shell_config
    shell_config=$(detect_shell_config)
    
    echo ""
    echo -e "${GREEN}════════════════════════════════════════════${NC}"
    echo -e "${GREEN}  Freckle installed successfully!${NC}"
    echo -e "${GREEN}════════════════════════════════════════════${NC}"
    echo ""
    echo "Next steps:"
    echo ""
    echo "  1. Reload your shell (or open a new terminal):"
    echo -e "     ${BLUE}source $shell_config${NC}"
    echo ""
    echo "  2. Initialize freckle with your dotfiles:"
    echo -e "     ${BLUE}freckle init${NC}"
    echo ""
    echo "  3. Install your configured tools:"
    echo -e "     ${BLUE}freckle tools install --all${NC}"
    echo ""
    echo "For more information, run:"
    echo -e "     ${BLUE}freckle --help${NC}"
    echo ""
}

# Main
main() {
    echo ""
    echo -e "${BLUE}╔═══════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║         Freckle Bootstrap Script          ║${NC}"
    echo -e "${BLUE}╚═══════════════════════════════════════════╝${NC}"
    echo ""
    
    check_requirements
    echo ""
    install_uv
    echo ""
    install_freckle
    print_next_steps
}

main "$@"
