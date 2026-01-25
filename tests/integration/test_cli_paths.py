"""Integration tests for CLI path handling.

These tests verify that freckle commands work correctly regardless of
the current working directory, testing the fixes for:
- v0.2.1: resolve dotfiles path relative to home directory
- v0.2.2: freckle add accepts paths relative to cwd
- v0.2.3: run git commands from work_tree directory
"""

import os
import subprocess
from pathlib import Path


def _create_bare_repo_with_files(tmp_path: Path, files: dict) -> Path:
    """Helper to create a bare repo with specified files."""
    bare_repo = tmp_path / "test_repo.git"
    subprocess.run(["git", "init", "--bare", str(bare_repo)], check=True, capture_output=True)
    
    work_dir = tmp_path / "temp_work"
    work_dir.mkdir()
    
    subprocess.run(["git", "init"], cwd=work_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=work_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=work_dir, check=True, capture_output=True)
    
    for filename, content in files.items():
        file_path = work_dir / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)
    
    subprocess.run(["git", "add", "."], cwd=work_dir, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=work_dir, check=True, capture_output=True)
    subprocess.run(["git", "remote", "add", "origin", str(bare_repo)], cwd=work_dir, check=True, capture_output=True)
    subprocess.run(["git", "push", "origin", "HEAD:main"], cwd=work_dir, check=True, capture_output=True)
    
    return bare_repo


def _create_freckle_config(home: Path, bare_repo: Path, dotfiles_dir: str = ".dotfiles"):
    """Create a .freckle.yaml config file."""
    config_content = f"""dotfiles:
  repo_url: {bare_repo}
  branch: main
  dir: {dotfiles_dir}
modules:
  - dotfiles
"""
    (home / ".freckle.yaml").write_text(config_content)


def test_freckle_run_from_subdir(tmp_path):
    """Test that 'freckle run' works when executed from a subdirectory of home."""
    bare_repo = _create_bare_repo_with_files(tmp_path, {
        ".zshrc": "# zsh config from repo"
    })
    
    home = tmp_path / "home"
    home.mkdir()
    subdir = home / "projects" / "myapp"
    subdir.mkdir(parents=True)
    
    _create_freckle_config(home, bare_repo)
    
    env = os.environ.copy()
    env["HOME"] = str(home)
    
    original_cwd = os.getcwd()
    try:
        os.chdir(subdir)
        
        result = subprocess.run(
            ["python", "-m", "freckle", "run"],
            env=env,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        assert result.returncode == 0, f"freckle run failed: {result.stderr}"
        assert (home / ".zshrc").exists()
        assert (home / ".zshrc").read_text() == "# zsh config from repo"
    finally:
        os.chdir(original_cwd)


def test_freckle_status_from_tmp(tmp_path):
    """Test that 'freckle status' works when executed from /tmp."""
    bare_repo = _create_bare_repo_with_files(tmp_path, {
        ".zshrc": "# zsh"
    })
    
    home = tmp_path / "home"
    home.mkdir()
    dotfiles_dir = home / ".dotfiles"
    
    _create_freckle_config(home, bare_repo)
    
    # Set up the dotfiles first
    from freckle.dotfiles import DotfilesManager
    manager = DotfilesManager(str(bare_repo), dotfiles_dir, home, branch="main")
    manager.setup()
    
    env = os.environ.copy()
    env["HOME"] = str(home)
    
    # Run from a completely unrelated directory
    unrelated = tmp_path / "somewhere_else"
    unrelated.mkdir()
    
    original_cwd = os.getcwd()
    try:
        os.chdir(unrelated)
        
        result = subprocess.run(
            ["python", "-m", "freckle", "status"],
            env=env,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        assert result.returncode == 0, f"freckle status failed: {result.stderr}"
        assert "freckle Status" in result.stdout
    finally:
        os.chdir(original_cwd)


def test_freckle_add_relative_path_from_subdir(tmp_path):
    """Test 'freckle add' with a path relative to cwd (not home)."""
    bare_repo = _create_bare_repo_with_files(tmp_path, {
        ".zshrc": "# zsh"
    })
    
    home = tmp_path / "home"
    home.mkdir()
    dotfiles_dir = home / ".dotfiles"
    
    # Create the file we want to add
    config_dir = home / ".config" / "starship"
    config_dir.mkdir(parents=True)
    (config_dir / "starship.toml").write_text("# starship config")
    
    _create_freckle_config(home, bare_repo)
    
    # Set up dotfiles
    from freckle.dotfiles import DotfilesManager
    manager = DotfilesManager(str(bare_repo), dotfiles_dir, home, branch="main")
    manager.setup()
    
    env = os.environ.copy()
    env["HOME"] = str(home)
    
    # Run from ~/.config (so ../starship/starship.toml would NOT work if paths aren't converted)
    subdir = home / "Documents"
    subdir.mkdir()
    
    original_cwd = os.getcwd()
    try:
        os.chdir(subdir)
        
        # Use path relative to cwd that goes up then into .config
        result = subprocess.run(
            ["python", "-m", "freckle", "add", "../.config/starship/starship.toml"],
            env=env,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        assert result.returncode == 0, f"freckle add failed: {result.stderr}"
        assert "Staged" in result.stdout or "staged" in result.stdout.lower()
    finally:
        os.chdir(original_cwd)


def test_freckle_add_absolute_path(tmp_path):
    """Test 'freckle add' with an absolute path."""
    bare_repo = _create_bare_repo_with_files(tmp_path, {
        ".zshrc": "# zsh"
    })
    
    home = tmp_path / "home"
    home.mkdir()
    dotfiles_dir = home / ".dotfiles"
    
    # Create the file we want to add
    gitconfig = home / ".gitconfig"
    gitconfig.write_text("[user]\nname = Test")
    
    _create_freckle_config(home, bare_repo)
    
    # Set up dotfiles
    from freckle.dotfiles import DotfilesManager
    manager = DotfilesManager(str(bare_repo), dotfiles_dir, home, branch="main")
    manager.setup()
    
    env = os.environ.copy()
    env["HOME"] = str(home)
    
    # Run from /tmp with absolute path
    original_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        
        result = subprocess.run(
            ["python", "-m", "freckle", "add", str(gitconfig)],
            env=env,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        assert result.returncode == 0, f"freckle add failed: {result.stderr}"
        assert "Staged" in result.stdout or "staged" in result.stdout.lower()
    finally:
        os.chdir(original_cwd)


def test_freckle_add_tilde_path(tmp_path):
    """Test 'freckle add' with a ~ prefixed path."""
    bare_repo = _create_bare_repo_with_files(tmp_path, {
        ".zshrc": "# zsh"
    })
    
    home = tmp_path / "home"
    home.mkdir()
    dotfiles_dir = home / ".dotfiles"
    
    # Create the file we want to add
    bashrc = home / ".bashrc"
    bashrc.write_text("# bashrc")
    
    _create_freckle_config(home, bare_repo)
    
    # Set up dotfiles
    from freckle.dotfiles import DotfilesManager
    manager = DotfilesManager(str(bare_repo), dotfiles_dir, home, branch="main")
    manager.setup()
    
    env = os.environ.copy()
    env["HOME"] = str(home)
    
    original_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        
        # This uses ~ which should expand to the fake home
        result = subprocess.run(
            ["python", "-m", "freckle", "add", "~/.bashrc"],
            env=env,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        assert result.returncode == 0, f"freckle add failed: {result.stderr}"
        assert "Staged" in result.stdout or "staged" in result.stdout.lower()
    finally:
        os.chdir(original_cwd)


def test_relative_dotfiles_dir_config(tmp_path):
    """Test that a relative dotfiles.dir config works from any cwd.
    
    This tests the v0.2.1 fix: relative paths like '.dotfiles' should
    resolve to ~/.dotfiles, not ./dotfiles (relative to cwd).
    """
    bare_repo = _create_bare_repo_with_files(tmp_path, {
        ".zshrc": "# zsh"
    })
    
    home = tmp_path / "home"
    home.mkdir()
    
    # Use relative path in config (the problematic case before v0.2.1)
    _create_freckle_config(home, bare_repo, dotfiles_dir=".dotfiles")
    
    env = os.environ.copy()
    env["HOME"] = str(home)
    
    # Create a subdirectory that does NOT contain .dotfiles
    subdir = home / "projects"
    subdir.mkdir()
    
    original_cwd = os.getcwd()
    try:
        os.chdir(subdir)
        
        # This should create ~/.dotfiles, not ~/projects/.dotfiles
        result = subprocess.run(
            ["python", "-m", "freckle", "run"],
            env=env,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        assert result.returncode == 0, f"freckle run failed: {result.stderr}"
        
        # Dotfiles should be at ~/.dotfiles, not ~/projects/.dotfiles
        assert (home / ".dotfiles").exists(), ".dotfiles should be in home"
        assert not (subdir / ".dotfiles").exists(), ".dotfiles should NOT be in cwd"
        assert (home / ".zshrc").exists()
    finally:
        os.chdir(original_cwd)
