import platform
import os
from freckle.system import Environment, OS

def test_detect_linux(mocker):
    mocker.patch("platform.system", return_value="Linux")
    env = Environment()
    assert env.os == OS.LINUX
    assert env.is_linux() is True
    assert env.is_macos() is False

def test_detect_macos(mocker):
    mocker.patch("platform.system", return_value="Darwin")
    env = Environment()
    assert env.os == OS.MACOS
    assert env.is_macos() is True
    assert env.is_linux() is False

def test_user_detection(mocker):
    mocker.patch.dict(os.environ, {"USER": "testuser"})
    env = Environment()
    assert env.user == "testuser"

def test_user_detection_fallback(mocker):
    # Mock USER and LOGNAME to be missing, should fallback to home name
    mocker.patch.dict(os.environ, {}, clear=True)
    from pathlib import Path
    mocker.patch("pathlib.Path.home", return_value=Path("/home/fallbackuser"))
    # We need to be careful with how Environment initialized home
    # Let's just mock the attribute directly if needed, but better to mock Path.home
    env = Environment()
    # Path("/home/fallbackuser").name is "fallbackuser"
    assert env.user == "fallbackuser"
