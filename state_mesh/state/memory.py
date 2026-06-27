from __future__ import annotations

from typing import Any

from state_mesh.state.base import StateBackend


class InMemoryBackend(StateBackend):
    def __init__(self):
        self._store: dict[str, Any] = {}

    async def save(self, run_id: str, state: Any) -> None:
        self._store[run_id] = state

    async def load(self, run_id: str) -> Any:
        return self._store.get(run_id)

    async def delete(self, run_id: str) -> None:
        self._store.pop(run_id, None)
