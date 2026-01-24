import shutil
import os
from pathlib import Path
from bootstrap.dotfiles import DotfilesManager
from git import GitCommandError

def test_dotfiles_backup_on_conflict(mocker, tmp_path):
    # Setup paths
    repo_url = "https://github.com/user/dots.git"
    dotfiles_dir = tmp_path / "dots_bare"
    work_tree = tmp_path / "home"
    work_tree.mkdir()
    
    # Create a conflicting file in the "home" directory
    conflicting_file = work_tree / ".zshrc"
    conflicting_file.write_text("old content")
    
    # Mock Repo and GitCommandError
    mock_repo_class = mocker.patch("bootstrap.dotfiles.Repo")
    mock_repo = mock_repo_class.return_value
    
    # Simulate first checkout failing with conflict
    # and second checkout succeeding
    error_msg = "The following untracked working tree files would be overwritten by checkout:\n  .zshrc\nPlease move or remove them before you switch branches."
    mock_repo.git.checkout.side_effect = [
        GitCommandError("checkout", 1, stderr=error_msg),
        None # Success on second call
    ]
    
    manager = DotfilesManager(repo_url, dotfiles_dir, work_tree)
    # We need to bypass setup() and just test _checkout_with_retry
    manager._checkout_with_retry(mock_repo)
    
    # Verify backup
    # Backup dir should start with .dotfiles_backup_
    backup_dirs = list(work_tree.glob(".dotfiles_backup_*"))
    assert len(backup_dirs) == 1
    backup_dir = backup_dirs[0]
    
    assert (backup_dir / ".zshrc").exists()
    assert (backup_dir / ".zshrc").read_text() == "old content"
    assert not conflicting_file.exists() # Should have been moved
    
    # Verify checkout was called twice
    assert mock_repo.git.checkout.call_count == 2
