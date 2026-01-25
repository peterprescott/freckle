"""End-to-end tests for freckle.

These tests simulate real user workflows including running freckle
from various directories to ensure cwd-independence.
"""

import subprocess
import os
import shutil
from pathlib import Path


def _setup_mock_remote(tmp_path: Path, files: dict) -> Path:
    """Create a bare git repo with initial files.
    
    Args:
        tmp_path: Base temporary directory
        files: Dict of {filename: content} to commit
        
    Returns:
        Path to the bare repository
    """
    remote_repo = tmp_path / "remote_dots.git"
    subprocess.run(["git", "init", "--bare", str(remote_repo)], check=True, capture_output=True)
    
    temp_worktree = tmp_path / "temp_worktree"
    temp_worktree.mkdir()
    subprocess.run(["git", "init"], cwd=temp_worktree, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=temp_worktree, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=temp_worktree, check=True, capture_output=True)
    
    for filename, content in files.items():
        file_path = temp_worktree / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)
    
    subprocess.run(["git", "add", "."], cwd=temp_worktree, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=temp_worktree, check=True, capture_output=True)
    subprocess.run(["git", "remote", "add", "origin", str(remote_repo)], cwd=temp_worktree, check=True, capture_output=True)
    subprocess.run(["git", "push", "origin", "master:main"], cwd=temp_worktree, check=True, capture_output=True)
    
    return remote_repo


def _create_env(home: Path) -> dict:
    """Create environment variables for tests."""
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["USER"] = "testuser"
    env["FRECKLE_MOCK_PKGS"] = "1"
    return env


def test_full_freckle_flow(tmp_path):
    """
    E2E test that simulates a full user workflow:
    1. Create a mock remote dotfiles repo
    2. Run freckle init
    3. Run freckle run
    4. Verify files are correctly placed and configured
    """
    home = tmp_path / "fake_home"
    home.mkdir()
    
    # Mock environment variables
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["USER"] = "testuser"
    env["FRECKLE_MOCK_PKGS"] = "1"
    
    # 1. Setup mock remote repo
    remote_repo = tmp_path / "remote_dots.git"
    subprocess.run(["git", "init", "--bare", str(remote_repo)], check=True)
    
    # Push initial content to mock remote
    temp_worktree = tmp_path / "temp_worktree"
    temp_worktree.mkdir()
    subprocess.run(["git", "init"], cwd=temp_worktree, check=True)
    (temp_worktree / ".zshrc").write_text("# mock zshrc")
    (temp_worktree / ".tmux.conf").write_text("# mock tmux")
    subprocess.run(["git", "add", "."], cwd=temp_worktree, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=temp_worktree, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=temp_worktree, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=temp_worktree, check=True)
    subprocess.run(["git", "remote", "add", "origin", str(remote_repo)], cwd=temp_worktree, check=True)
    subprocess.run(["git", "push", "origin", "master:main"], cwd=temp_worktree, check=True)

    # 2. Run freckle init
    # We'll use the CLI directly. 'freckle' should be in the path if installed via uv.
    # Alternatively, we can use 'uv run freckle'
    # Input: y (clone existing), repo URL, branch, dotfiles dir
    init_input = f"y\n{remote_repo}\nmain\n{home}/.dotfiles\n"
    subprocess.run(
        ["uv", "run", "freckle", "init"],
        input=init_input,
        text=True,
        env=env,
        check=True
    )
    
    assert (home / ".freckle.yaml").exists()

    # 3. Run freckle run
    subprocess.run(
        ["uv", "run", "freckle", "run"],
        env=env,
        check=True
    )

    # 4. Verify results
    assert (home / ".zshrc").exists()
    assert (home / ".zshrc").read_text() == "# mock zshrc"
    assert (home / ".tmux.conf").exists()
    assert (home / ".tmux.conf").read_text() == "# mock tmux"
    assert (home / ".dotfiles").exists()
    assert (home / ".dotfiles").is_dir()

    # Verify nvim setup (lazy.nvim installation)
    # The NvimManager should still clone lazy.nvim
    assert (home / ".local/share/nvim/lazy/lazy.nvim").exists()


def test_full_flow_from_subdirectory(tmp_path):
    """
    E2E test running the full workflow from a subdirectory of home.
    
    This tests the fixes from v0.2.1-v0.2.3 where freckle would fail
    when run from anywhere other than ~.
    """
    home = tmp_path / "fake_home"
    home.mkdir()
    
    # Create a subdirectory to run from (simulating ~/projects/myapp)
    subdir = home / "projects" / "myapp"
    subdir.mkdir(parents=True)
    
    env = _create_env(home)
    remote_repo = _setup_mock_remote(tmp_path, {
        ".zshrc": "# zshrc from remote",
        ".tmux.conf": "# tmux from remote",
        ".config/nvim/init.lua": "-- nvim config"
    })
    
    original_cwd = os.getcwd()
    try:
        # Change to the subdirectory BEFORE running any freckle commands
        os.chdir(subdir)
        
        # Run freckle init from ~/projects/myapp
        init_input = f"y\n{remote_repo}\nmain\n.dotfiles\n"
        result = subprocess.run(
            ["python", "-m", "freckle", "init"],
            input=init_input,
            text=True,
            env=env,
            capture_output=True,
            timeout=30
        )
        assert result.returncode == 0, f"init failed: {result.stderr}"
        assert (home / ".freckle.yaml").exists()
        
        # Run freckle run from ~/projects/myapp
        result = subprocess.run(
            ["python", "-m", "freckle", "run"],
            env=env,
            capture_output=True,
            text=True,
            timeout=60
        )
        assert result.returncode == 0, f"run failed: {result.stderr}"
        
        # Verify dotfiles were checked out to ~ (not ~/projects/myapp)
        assert (home / ".zshrc").exists()
        assert (home / ".zshrc").read_text() == "# zshrc from remote"
        assert (home / ".config/nvim/init.lua").exists()
        
        # Verify .dotfiles is in ~ (not in cwd)
        assert (home / ".dotfiles").exists()
        assert not (subdir / ".dotfiles").exists()
        
        # Run freckle status from ~/projects/myapp
        result = subprocess.run(
            ["python", "-m", "freckle", "status"],
            env=env,
            capture_output=True,
            text=True,
            timeout=30
        )
        assert result.returncode == 0, f"status failed: {result.stderr}"
        assert "freckle Status" in result.stdout
        
    finally:
        os.chdir(original_cwd)


def test_add_and_backup_from_different_directories(tmp_path):
    """
    E2E test for the add -> backup workflow from various directories.
    
    Tests:
    1. freckle add from a subdirectory with relative paths
    2. freckle add from /tmp with absolute paths
    3. freckle run --backup from a subdirectory
    """
    home = tmp_path / "fake_home"
    home.mkdir()
    
    env = _create_env(home)
    remote_repo = _setup_mock_remote(tmp_path, {
        ".zshrc": "# initial zshrc"
    })
    
    # Set up freckle first (from home, to establish baseline)
    original_cwd = os.getcwd()
    try:
        os.chdir(home)
        
        init_input = f"y\n{remote_repo}\nmain\n.dotfiles\n"
        subprocess.run(
            ["python", "-m", "freckle", "init"],
            input=init_input,
            text=True,
            env=env,
            capture_output=True,
            check=True,
            timeout=30
        )
        subprocess.run(
            ["python", "-m", "freckle", "run"],
            env=env,
            capture_output=True,
            check=True,
            timeout=60
        )
        
        # Create files to add
        (home / ".gitconfig").write_text("[user]\nname = Test")
        config_dir = home / ".config" / "starship"
        config_dir.mkdir(parents=True)
        (config_dir / "starship.toml").write_text("# starship config")
        
        # --- Test 1: Add from subdirectory with relative path ---
        subdir = home / "code"
        subdir.mkdir()
        os.chdir(subdir)
        
        # Add ../.gitconfig (relative to ~/code)
        result = subprocess.run(
            ["python", "-m", "freckle", "add", "../.gitconfig"],
            env=env,
            capture_output=True,
            text=True,
            timeout=30
        )
        assert result.returncode == 0, f"add failed: {result.stderr}"
        assert "Staged" in result.stdout
        
        # --- Test 2: Add from /tmp with absolute path ---
        os.chdir(tmp_path)
        
        result = subprocess.run(
            ["python", "-m", "freckle", "add", str(home / ".config/starship/starship.toml")],
            env=env,
            capture_output=True,
            text=True,
            timeout=30
        )
        assert result.returncode == 0, f"add absolute failed: {result.stderr}"
        assert "Staged" in result.stdout
        
        # --- Test 3: Backup from subdirectory ---
        os.chdir(subdir)
        
        result = subprocess.run(
            ["python", "-m", "freckle", "run", "--backup"],
            env=env,
            capture_output=True,
            text=True,
            timeout=60
        )
        assert result.returncode == 0, f"backup failed: {result.stderr}"
        # Should mention backup success or no changes (if already committed)
        
    finally:
        os.chdir(original_cwd)


def test_init_new_repo_from_subdirectory(tmp_path):
    """
    E2E test creating a new dotfiles repo from a subdirectory.
    
    Tests the "create new" flow when user doesn't have existing dotfiles.
    We skip the interactive init and create config directly to test
    that the repo creation works from a subdirectory.
    """
    home = tmp_path / "fake_home"
    home.mkdir()
    
    # Create initial files
    (home / ".zshrc").write_text("# my zshrc")
    (home / ".gitconfig").write_text("[user]\nname = Me")
    
    # Create subdirectory to run from
    subdir = home / "Downloads"
    subdir.mkdir()
    
    env = _create_env(home)
    
    # Create config manually (the interactive init has too many conditional prompts)
    config_content = """dotfiles:
  repo_url: file:///dev/null
  branch: main
  dir: .dotfiles
modules:
  - dotfiles
"""
    (home / ".freckle.yaml").write_text(config_content)
    
    original_cwd = os.getcwd()
    try:
        os.chdir(subdir)
        
        # Use DotfilesManager directly to test create_new from subdirectory
        from freckle.dotfiles import DotfilesManager
        
        dotfiles_dir = home / ".dotfiles"
        manager = DotfilesManager("", dotfiles_dir, home, branch="main")
        manager.create_new(initial_files=[".zshrc", ".gitconfig"])
        
        # Verify dotfiles repo is in home, not in cwd
        assert (home / ".dotfiles").exists(), ".dotfiles should be in home"
        assert not (subdir / ".dotfiles").exists(), ".dotfiles should NOT be in cwd"
        
        # Verify we can run status from the subdirectory
        result = subprocess.run(
            ["python", "-m", "freckle", "status"],
            env=env,
            capture_output=True,
            text=True,
            timeout=30
        )
        assert result.returncode == 0, f"status failed: {result.stderr}"
        
    finally:
        os.chdir(original_cwd)


def test_status_shows_correct_info_from_anywhere(tmp_path):
    """
    E2E test that status shows accurate information regardless of cwd.
    """
    home = tmp_path / "fake_home"
    home.mkdir()
    
    env = _create_env(home)
    remote_repo = _setup_mock_remote(tmp_path, {
        ".zshrc": "# zshrc"
    })
    
    # Set up freckle
    original_cwd = os.getcwd()
    try:
        os.chdir(home)
        
        init_input = f"y\n{remote_repo}\nmain\n.dotfiles\n"
        subprocess.run(
            ["python", "-m", "freckle", "init"],
            input=init_input,
            text=True,
            env=env,
            capture_output=True,
            check=True,
            timeout=30
        )
        subprocess.run(
            ["python", "-m", "freckle", "run"],
            env=env,
            capture_output=True,
            check=True,
            timeout=60
        )
        
        # Modify a file to create local changes
        (home / ".zshrc").write_text("# modified zshrc")
        
        # Check status from multiple locations
        for location in [home, home / "subdir", tmp_path]:
            location.mkdir(exist_ok=True)
            os.chdir(location)
            
            result = subprocess.run(
                ["python", "-m", "freckle", "status"],
                env=env,
                capture_output=True,
                text=True,
                timeout=30
            )
            assert result.returncode == 0, f"status failed from {location}: {result.stderr}"
            assert "freckle Status" in result.stdout
            # Should show the modified file regardless of cwd
            assert "modified" in result.stdout.lower() or ".zshrc" in result.stdout
            
    finally:
        os.chdir(original_cwd)
