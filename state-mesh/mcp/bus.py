from __future__ import annotations

from typing import Any

from client import MCPClient
from registry import MCPRegistry


class MCPBus:
    def __init__(self, server_urls: list[str]):
        self._clients = [MCPClient(url) for url in server_urls]
        self._registry = MCPRegistry()

    async def start(self) -> None:
        for client in self._clients:
            await client.connect()
            self._registry.register(client)

    async def stop(self) -> None:
        for client in self._clients:
            await client.disconnect()

    async def call(self, tool_name: str, args: dict[str, Any]) -> Any:
        client = self._registry.get_client(tool_name)
        return await client.call_tool(tool_name, args)
