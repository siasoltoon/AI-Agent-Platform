from abc import ABC, abstractmethod


class BaseTool(ABC):
    """Base contract for every agent tool."""

    name = "base"

    @abstractmethod
    def execute(self, **kwargs):
        raise NotImplementedError
