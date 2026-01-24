import subprocess
import os
import shutil
from pathlib import Path

def test_full_bootstrap_flow(tmp_path):
    """
    E2E test that simulates a full user workflow:
    1. Create a mock remote dotfiles repo
    2. Run bootstrap init
    3. Run bootstrap run
    4. Verify files are correctly placed and configured
    """
    home = tmp_path / "fake_home"
    home.mkdir()
    
    # Mock environment variables
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["USER"] = "testuser"
    env["BOOTSTRAP_MOCK_PKGS"] = "1"
    
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

    # 2. Run bootstrap init
    # We'll use the CLI directly. 'bootstrap' should be in the path if installed via uv.
    # Alternatively, we can use 'uv run bootstrap'
    init_input = f"{remote_repo}\nmain\n{home}/.dotfiles\n"
    subprocess.run(
        ["uv", "run", "bootstrap", "init"],
        input=init_input,
        text=True,
        env=env,
        check=True
    )
    
    assert (home / ".bootstrap.yaml").exists()

    # 3. Run bootstrap run
    subprocess.run(
        ["uv", "run", "bootstrap", "run"],
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
