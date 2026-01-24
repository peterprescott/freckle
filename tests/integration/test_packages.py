import subprocess
from bootstrap.packages import PackageManager

def test_install_apt_linux(mocker):
    # Mock environment to be Linux
    mock_env = mocker.Mock()
    mock_env.is_linux.return_value = True
    mock_env.is_macos.return_value = False
    
    mock_run = mocker.patch("subprocess.run")
    
    pkg_mgr = PackageManager(mock_env)
    pkg_mgr.install("htop")
    
    # Verify apt commands were called
    # Should call sudo apt update and sudo apt install -y htop
    assert mock_run.call_count == 2
    mock_run.assert_any_call(["sudo", "apt", "update"], check=True)
    mock_run.assert_any_call(["sudo", "apt", "install", "-y", "htop"], check=True)

def test_install_brew_macos(mocker):
    # Mock environment to be macOS
    mock_env = mocker.Mock()
    mock_env.is_linux.return_value = False
    mock_env.is_macos.return_value = True
    
    mocker.patch("shutil.which", return_value="/usr/local/bin/brew")
    mock_run = mocker.patch("subprocess.run")
    
    pkg_mgr = PackageManager(mock_env)
    pkg_mgr.install("htop")
    
    # Verify brew command was called
    mock_run.assert_called_once_with(["brew", "install", "htop"], check=True)

def test_get_binary_info_found(mocker):
    mock_env = mocker.Mock()
    mocker.patch("shutil.which", return_value="/usr/bin/zsh")
    
    # Mock subprocess.run to return a version string
    mock_result = mocker.Mock()
    mock_result.returncode = 0
    mock_result.stdout = "zsh 5.8 (x86_64-debian-linux-gnu)\nother lines"
    mocker.patch("subprocess.run", return_value=mock_result)
    
    pkg_mgr = PackageManager(mock_env)
    info = pkg_mgr.get_binary_info("zsh")
    
    assert info["found"] is True
    assert info["path"] == "/usr/bin/zsh"
    assert info["version"] == "zsh 5.8 (x86_64-debian-linux-gnu)"

def test_get_binary_info_not_found(mocker):
    mock_env = mocker.Mock()
    mocker.patch("shutil.which", return_value=None)
    
    pkg_mgr = PackageManager(mock_env)
    info = pkg_mgr.get_binary_info("nonexistent")
    
    assert info["found"] is False
