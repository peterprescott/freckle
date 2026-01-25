"""Integration tests for DotfilesManager with pygit2."""

import subprocess
from pathlib import Path
from bootstrap.dotfiles import DotfilesManager


def _create_bare_repo_with_files(tmp_path: Path, files: dict) -> Path:
    """Helper to create a bare repo with specified files.
    
    Args:
        tmp_path: Temporary directory
        files: Dict of {filename: content}
        
    Returns:
        Path to the bare repository
    """
    # Create a bare repo
    bare_repo = tmp_path / "test_repo.git"
    subprocess.run(["git", "init", "--bare", str(bare_repo)], check=True, capture_output=True)
    
    # Create a temp working directory to add files
    work_dir = tmp_path / "temp_work"
    work_dir.mkdir()
    
    subprocess.run(["git", "init"], cwd=work_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=work_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=work_dir, check=True, capture_output=True)
    
    # Create files
    for filename, content in files.items():
        file_path = work_dir / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)
    
    subprocess.run(["git", "add", "."], cwd=work_dir, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=work_dir, check=True, capture_output=True)
    subprocess.run(["git", "remote", "add", "origin", str(bare_repo)], cwd=work_dir, check=True, capture_output=True)
    subprocess.run(["git", "push", "origin", "master:main"], cwd=work_dir, check=True, capture_output=True)
    
    return bare_repo


def test_dotfiles_backup_on_conflict(tmp_path):
    """Test that existing files are backed up during initial setup."""
    # Create a bare repo with .zshrc
    bare_repo = _create_bare_repo_with_files(tmp_path, {
        ".zshrc": "# From repo",
        ".tmux.conf": "# tmux config"
    })
    
    # Create work tree with existing conflicting file
    work_tree = tmp_path / "home"
    work_tree.mkdir()
    existing_zshrc = work_tree / ".zshrc"
    existing_zshrc.write_text("# My existing zshrc")
    
    # Create dotfiles directory (will be the bare clone destination)
    dotfiles_dir = tmp_path / "dotfiles_bare"
    
    # Run setup
    manager = DotfilesManager(str(bare_repo), dotfiles_dir, work_tree, branch="main")
    manager.setup()
    
    # Verify backup was created
    backup_dirs = list(work_tree.glob(".dotfiles_backup_*"))
    assert len(backup_dirs) == 1
    backup_dir = backup_dirs[0]
    
    # Verify the original file was backed up
    assert (backup_dir / ".zshrc").exists()
    assert (backup_dir / ".zshrc").read_text() == "# My existing zshrc"
    
    # Verify repo version is now in place
    assert existing_zshrc.read_text() == "# From repo"
    
    # Verify other files were checked out
    assert (work_tree / ".tmux.conf").exists()
    assert (work_tree / ".tmux.conf").read_text() == "# tmux config"


def test_get_tracked_files(tmp_path):
    """Test _get_tracked_files returns correct file list."""
    bare_repo = _create_bare_repo_with_files(tmp_path, {
        ".zshrc": "zsh config",
        ".config/nvim/init.lua": "nvim config",
        ".tmux.conf": "tmux config"
    })
    
    work_tree = tmp_path / "home"
    work_tree.mkdir()
    dotfiles_dir = tmp_path / "dotfiles"
    
    manager = DotfilesManager(str(bare_repo), dotfiles_dir, work_tree, branch="main")
    manager._get_repo()  # Initialize repo
    manager._fetch()
    
    tracked = manager._get_tracked_files()
    assert sorted(tracked) == sorted([".zshrc", ".config/nvim/init.lua", ".tmux.conf"])


def test_file_sync_status(tmp_path):
    """Test get_file_sync_status returns correct status for various scenarios."""
    bare_repo = _create_bare_repo_with_files(tmp_path, {
        ".zshrc": "original content",
        ".tmux.conf": "tmux config"
    })
    
    work_tree = tmp_path / "home"
    work_tree.mkdir()
    dotfiles_dir = tmp_path / "dotfiles"
    
    manager = DotfilesManager(str(bare_repo), dotfiles_dir, work_tree, branch="main")
    manager.setup()
    
    # 1. up-to-date: file matches HEAD
    assert manager.get_file_sync_status(".zshrc") == "up-to-date"
    
    # 2. modified: change the local file
    (work_tree / ".zshrc").write_text("modified content")
    assert manager.get_file_sync_status(".zshrc") == "modified"
    
    # 3. missing: delete the local file
    (work_tree / ".tmux.conf").unlink()
    assert manager.get_file_sync_status(".tmux.conf") == "missing"
    
    # 4. not-found: file that doesn't exist anywhere
    assert manager.get_file_sync_status("nonexistent") == "not-found"
    
    # 5. untracked: file exists locally but not in repo
    (work_tree / "untracked_file").write_text("untracked")
    assert manager.get_file_sync_status("untracked_file") == "untracked"


def test_get_detailed_status(tmp_path):
    """Test get_detailed_status returns correct information."""
    bare_repo = _create_bare_repo_with_files(tmp_path, {
        ".zshrc": "zsh config"
    })
    
    work_tree = tmp_path / "home"
    work_tree.mkdir()
    dotfiles_dir = tmp_path / "dotfiles"
    
    manager = DotfilesManager(str(bare_repo), dotfiles_dir, work_tree, branch="main")
    manager.setup()
    
    # Initially should be up to date
    status = manager.get_detailed_status()
    assert status["initialized"] is True
    assert status["has_local_changes"] is False
    assert status["is_ahead"] is False
    assert status["is_behind"] is False
    assert len(status["changed_files"]) == 0
    
    # Modify a file
    (work_tree / ".zshrc").write_text("modified content")
    
    status = manager.get_detailed_status()
    assert status["has_local_changes"] is True
    assert ".zshrc" in status["changed_files"]


def test_not_initialized_status(tmp_path):
    """Test status when repo doesn't exist."""
    work_tree = tmp_path / "home"
    work_tree.mkdir()
    dotfiles_dir = tmp_path / "dotfiles"  # Doesn't exist
    
    manager = DotfilesManager("https://example.com/repo.git", dotfiles_dir, work_tree)
    
    status = manager.get_detailed_status()
    assert status["initialized"] is False
    
    file_status = manager.get_file_sync_status(".zshrc")
    assert file_status == "not-initialized"
