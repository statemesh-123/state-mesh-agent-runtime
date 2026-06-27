from __future__ import annotations

from state_mesh.mcp.client import MCPClient


class ToolNotFoundError(Exception):
    pass


class MCPRegistry:
    def __init__(self):
        self._map: dict[str, MCPClient] = {}

    def register(self, client: MCPClient) -> None:
        for tool in client.tools:
            if tool in self._map:
                existing = self._map.pop(tool)
                self._map[f"{existing.server_url}.{tool}"] = existing
                self._map[f"{client.server_url}.{tool}"] = client
            else:
                self._map[tool] = client

    def get_client(self, tool_name: str) -> MCPClient:
        if tool_name not in self._map:
            raise ToolNotFoundError(f"No client found for tool '{tool_name}'")
        return self._map[tool_name]
