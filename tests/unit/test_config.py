from freckle.config import Config


def test_config_defaults():
    config = Config()
    assert config.get("dotfiles.branch") == "main"
    assert config.get("dotfiles.repo_url") is None

def test_config_templating(mocker):
    # Mock environment with a specific user
    mock_env = mocker.Mock()
    mock_env.user = "testuser"

    # Config with a template
    user_config = {
        "dotfiles": {
            "repo_url": "https://github.com/{local_user}/dots.git"
        }
    }

    # We can't easily pass user_config to __init__ without a file,
    # so let's mock the yaml loading or use a temporary file.
    # Actually, Config._deep_update is public-ish enough to use for testing.

    config = Config(env=mock_env)
    config._deep_update(config.data, user_config)
    config._apply_replacements(config.data)

    assert config.get("dotfiles.repo_url") == "https://github.com/testuser/dots.git"

def test_custom_vars(mocker):
    mock_env = mocker.Mock()
    mock_env.user = "localuser"

    user_config = {
        "vars": {
            "git_host": "gitlab.com",
            "git_user": "gituser"
        },
        "dotfiles": {
            "repo_url": "https://{git_host}/{git_user}/repo.git"
        }
    }

    config = Config(env=mock_env)
    config._deep_update(config.data, user_config)
    config._apply_replacements(config.data)

    assert config.get("dotfiles.repo_url") == "https://gitlab.com/gituser/repo.git"

def test_deep_merge():
    config = Config()
    update = {
        "dotfiles": {
            "branch": "develop"
        },
        "modules": ["dotfiles"]
    }
    config._deep_update(config.data, update)

    assert config.get("dotfiles.branch") == "develop"
    assert config.get("dotfiles.dir") == "~/.dotfiles" # Should preserve other defaults
    assert config.get("modules") == ["dotfiles"] # Lists should be replaced
