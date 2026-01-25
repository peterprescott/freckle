FROM debian:stable-slim

# Avoid prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Install dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    sudo \
    python3 \
    python3-pip \
    python3-venv \
    zsh \
    tmux \
    neovim \
    && rm -rf /var/lib/apt/lists/*

# Install uv - copy from official image and set permissions separately
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uv
RUN chmod 755 /uv
ENV PATH="/:$PATH"

# Create a test user
RUN useradd -m -s /bin/bash testuser && \
    echo "testuser ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

USER testuser
WORKDIR /home/testuser

# Copy the freckle project
COPY --chown=testuser:testuser . /home/testuser/freckle

# Initialize a mock dotfiles repo for testing
RUN mkdir -p /home/testuser/mock-dotfiles.git && \
    cd /home/testuser/mock-dotfiles.git && \
    git init --bare && \
    git config --global user.email "test@example.com" && \
    git config --global user.name "Test User"

# Setup dummy files in a temporary work tree to push to the bare repo
RUN mkdir -p /home/testuser/temp-dots && \
    cd /home/testuser/temp-dots && \
    git init && \
    echo "alias test='echo success'" > .zshrc && \
    git add .zshrc && \
    git commit -m "Initial commit" && \
    git remote add origin /home/testuser/mock-dotfiles.git && \
    git push origin master:main

# Pre-install the freckle tool
RUN cd /home/testuser/freckle && uv pip install .

# Set default command
CMD ["/bin/bash"]
