from __future__ import annotations

from typing import Any

from mcp import ClientSession
from mcp.client.sse import sse_client


class MCPClient:
    def __init__(self, server_url: str):
        self.server_url = server_url
        self._session: ClientSession | None = None
        self._sse_ctx = None
        self._session_ctx = None
        self._tools: list[str] = []

    async def connect(self) -> None:
        self._sse_ctx = sse_client(self.server_url)
        read, write = await self._sse_ctx.__aenter__()
        self._session_ctx = ClientSession(read, write)
        self._session = await self._session_ctx.__aenter__()
        await self._session.initialize()
        response = await self._session.list_tools()
        self._tools = [tool.name for tool in response.tools]

    async def disconnect(self) -> None:
        if self._session_ctx:
            await self._session_ctx.__aexit__(None, None, None)
        if self._sse_ctx:
            await self._sse_ctx.__aexit__(None, None, None)

    async def call_tool(self, name: str, args: dict[str, Any]) -> Any:
        if self._session is None:
            raise RuntimeError("Not connected. Call connect() first.")
        response = await self._session.call_tool(name, args)
        return response.content

    @property
    def tools(self) -> list[str]:
        return self._tools
