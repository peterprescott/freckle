from .base import BaseToolManager


class GitManager(BaseToolManager):
    @property
    def name(self) -> str:
        return "Git"

    @property
    def bin_name(self) -> str:
        return "git"

    @property
    def config_files(self) -> list:
        return [".gitconfig", ".config/git/config"]
