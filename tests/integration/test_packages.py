import subprocess
from bootstrap.packages import PackageManager

def test_install_apt_linux(mocker):
    # Mock environment to be Linux with Debian distro
    mock_env = mocker.Mock()
    mock_env.is_linux.return_value = True
    mock_env.is_macos.return_value = False
    mock_env.os_info = {"distro": "debian", "pretty_name": "Debian GNU/Linux"}
    
    mock_run = mocker.patch("subprocess.run")
    # Mock shutil.which to return sudo path
    mocker.patch("bootstrap.packages.shutil.which", return_value="/usr/bin/sudo")
    # Mock os.geteuid to return non-root
    mocker.patch("bootstrap.packages.os.geteuid", return_value=1000)
    
    pkg_mgr = PackageManager(mock_env)
    pkg_mgr.install("htop")
    
    # Verify apt commands were called with sudo
    # Should call sudo apt update and sudo apt install -y htop
    assert mock_run.call_count == 2
    mock_run.assert_any_call(["sudo", "apt", "update"], check=True)
    mock_run.assert_any_call(["sudo", "apt", "install", "-y", "htop"], check=True)


def test_install_apt_as_root(mocker):
    # Mock environment to be Linux with Debian distro, running as root
    mock_env = mocker.Mock()
    mock_env.is_linux.return_value = True
    mock_env.is_macos.return_value = False
    mock_env.os_info = {"distro": "ubuntu", "pretty_name": "Ubuntu 22.04"}
    
    mock_run = mocker.patch("subprocess.run")
    # Mock os.geteuid to return root
    mocker.patch("bootstrap.packages.os.geteuid", return_value=0)
    
    pkg_mgr = PackageManager(mock_env)
    pkg_mgr.install("htop")
    
    # Verify apt commands were called WITHOUT sudo (since we're root)
    assert mock_run.call_count == 2
    mock_run.assert_any_call(["apt", "update"], check=True)
    mock_run.assert_any_call(["apt", "install", "-y", "htop"], check=True)


def test_install_dnf_fedora(mocker):
    # Mock environment to be Fedora
    mock_env = mocker.Mock()
    mock_env.is_linux.return_value = True
    mock_env.is_macos.return_value = False
    mock_env.os_info = {"distro": "fedora", "pretty_name": "Fedora 39"}
    
    mock_run = mocker.patch("subprocess.run")
    mocker.patch("bootstrap.packages.shutil.which", return_value="/usr/bin/sudo")
    mocker.patch("bootstrap.packages.os.geteuid", return_value=1000)
    
    pkg_mgr = PackageManager(mock_env)
    pkg_mgr.install("htop")
    
    # Fedora uses dnf and doesn't need an update command before install
    assert mock_run.call_count == 1
    mock_run.assert_called_once_with(["sudo", "dnf", "install", "-y", "htop"], check=True)


def test_install_brew_macos(mocker):
    # Mock environment to be macOS
    mock_env = mocker.Mock()
    mock_env.is_linux.return_value = False
    mock_env.is_macos.return_value = True
    mock_env.os_info = {"distro": "macos", "pretty_name": "macOS 14.0"}
    
    mocker.patch("bootstrap.packages.shutil.which", return_value="/usr/local/bin/brew")
    mock_run = mocker.patch("subprocess.run")
    
    pkg_mgr = PackageManager(mock_env)
    pkg_mgr.install("htop")
    
    # Verify brew command was called
    mock_run.assert_called_once_with(["brew", "install", "htop"], check=True)


def test_get_binary_info_found(mocker):
    mock_env = mocker.Mock()
    mock_env.os_info = {}
    mocker.patch("bootstrap.packages.shutil.which", return_value="/usr/bin/zsh")
    
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
    mock_env.os_info = {}
    mocker.patch("bootstrap.packages.shutil.which", return_value=None)
    
    pkg_mgr = PackageManager(mock_env)
    info = pkg_mgr.get_binary_info("nonexistent")
    
    assert info["found"] is False
