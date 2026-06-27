from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class StateBackend(ABC):

    @abstractmethod
    async def save(self, run_id: str, state: Any) -> None:
        pass

    @abstractmethod
    async def load(self, run_id: str) -> Any:
        pass

    @abstractmethod
    async def delete(self, run_id: str) -> None:
        pass
