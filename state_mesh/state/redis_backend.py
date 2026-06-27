from __future__ import annotations

import json
from typing import Any

import redis.asyncio as aioredis

from state_mesh.state.base import StateBackend


class RedisStateBackend(StateBackend):
    def __init__(self, url: str, ttl: int =10800):
        self.url = url
        self.ttl = ttl
        self._client: aioredis.Redis = aioredis.from_url(url)

    async def save(self, run_id: str, state: Any) -> None:
        data = state.model_dump_json() if hasattr(state, "model_dump_json") else json.dumps(state)
        await self._client.set(run_id, data, ex=self.ttl)

    async def load(self, run_id: str) -> Any:
        data = await self._client.get(run_id)
        if data is None:
            return None
        return json.loads(data)

    async def delete(self, run_id: str) -> None:
        await self._client.delete(run_id)

    async def close(self) -> None:
        await self._client.aclose()
