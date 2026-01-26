from .base import BaseToolManager


class TmuxManager(BaseToolManager):
    @property
    def name(self) -> str:
        return "Tmux"

    @property
    def bin_name(self) -> str:
        return "tmux"

    @property
    def config_files(self) -> list:
        return [".tmux.conf"]
