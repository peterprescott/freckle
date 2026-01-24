import shutil
import os
from pathlib import Path
from bootstrap.dotfiles import DotfilesManager
from git import GitCommandError

def test_dotfiles_backup_on_conflict(mocker, tmp_path):
    # Setup paths
    repo_url = "https://github.com/user/dots.git"
    dotfiles_dir = tmp_path / "dots_bare"
    dotfiles_dir.mkdir() # Must exist
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
    mock_repo.git.execute.side_effect = [
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
    
    # Verify checkout was called twice via execute
    assert mock_repo.git.execute.call_count == 2

def test_file_sync_status(mocker, tmp_path):
    repo_url = "https://github.com/user/dots.git"
    dotfiles_dir = tmp_path / "dots_bare"
    dotfiles_dir.mkdir() # Must exist for status logic to proceed
    work_tree = tmp_path / "home"
    work_tree.mkdir()
    
    mock_repo_class = mocker.patch("bootstrap.dotfiles.Repo")
    mock_repo = mock_repo_class.return_value
    
    manager = DotfilesManager(repo_url, dotfiles_dir, work_tree, branch="main")
    
    # 1. Test: not-found (doesn't exist locally, not in repo)
    mock_repo.git.rev_parse.side_effect = GitCommandError("rev-parse", 1)
    assert manager.get_file_sync_status("nonexistent") == "not-found"
    
    # 2. Test: missing (in repo, but not local)
    mock_repo.git.rev_parse.side_effect = ["sha1_head", "sha1_remote"]
    assert manager.get_file_sync_status("missing_file") == "missing"
    
    # 3. Test: untracked (local, but not in repo)
    local_file = work_tree / "untracked_file"
    local_file.write_text("content")
    mock_repo.git.rev_parse.side_effect = GitCommandError("rev-parse", 1)
    assert manager.get_file_sync_status("untracked_file") == "untracked"
    
    # 4. Test: up-to-date (local matches remote)
    local_file = work_tree / "up_to_date_file"
    local_file.write_text("content")
    local_sha = "sha_local"
    # mock_repo.git.hash_object.return_value = local_sha
    # It calls repo.git.hash_object
    mock_repo.git.hash_object.return_value = local_sha
    mock_repo.git.rev_parse.side_effect = ["sha_head", local_sha] # head, remote
    assert manager.get_file_sync_status("up_to_date_file") == "up-to-date"
    
    # 5. Test: modified (local different from head)
    local_file = work_tree / "modified_file"
    local_file.write_text("new content")
    mock_repo.git.rev_parse.side_effect = ["sha_head", "sha_remote"]
    mock_repo.git.hash_object.return_value = "sha_new"
    assert manager.get_file_sync_status("modified_file") == "modified"
    
    # 6. Test: behind (local matches head, but remote is different)
    local_file = work_tree / "behind_file"
    local_file.write_text("old content")
    sha_old = "sha_old"
    mock_repo.git.hash_object.return_value = sha_old
    mock_repo.git.rev_parse.side_effect = [sha_old, "sha_new"] # head, remote
    assert manager.get_file_sync_status("behind_file") == "behind"
