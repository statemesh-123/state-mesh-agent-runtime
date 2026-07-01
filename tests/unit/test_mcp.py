import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from state_mesh.mcp.registry import MCPRegistry, ToolNotFoundError
from state_mesh.mcp.client import MCPClient
from state_mesh.mcp.bus import MCPBus


def make_mock_client(server_url: str, tools: list[str]) -> MCPClient:
    client = MCPClient.__new__(MCPClient)
    client.server_url = server_url
    client._tools = tools
    client._session = MagicMock()
    client._sse_ctx = None
    client._session_ctx = None
    client.connect = AsyncMock()
    client.disconnect = AsyncMock()
    client.call_tool = AsyncMock(return_value="result")
    return client


# --- registry ---

def test_registry_registers_single_client():
    registry = MCPRegistry()
    client = make_mock_client("http://server1", ["tool_a", "tool_b"])
    registry.register(client)
    assert registry.get_client("tool_a") is client
    assert registry.get_client("tool_b") is client


def test_registry_raises_for_unknown_tool():
    registry = MCPRegistry()
    with pytest.raises(ToolNotFoundError):
        registry.get_client("nonexistent")


def test_registry_namespaces_on_collision():
    registry = MCPRegistry()
    client1 = make_mock_client("http://server1", ["shared_tool"])
    client2 = make_mock_client("http://server2", ["shared_tool"])
    registry.register(client1)
    registry.register(client2)

    assert "shared_tool" not in registry._map
    assert registry.get_client("http://server1.shared_tool") is client1
    assert registry.get_client("http://server2.shared_tool") is client2


def test_registry_no_collision_for_unique_tools():
    registry = MCPRegistry()
    client1 = make_mock_client("http://server1", ["tool_a"])
    client2 = make_mock_client("http://server2", ["tool_b"])
    registry.register(client1)
    registry.register(client2)
    assert registry.get_client("tool_a") is client1
    assert registry.get_client("tool_b") is client2


# --- client ---

@pytest.mark.asyncio
async def test_client_call_tool_raises_when_not_connected():
    client = MCPClient("http://server1")
    with pytest.raises(RuntimeError, match="Not connected"):
        await client.call_tool("tool_a", {})


@pytest.mark.asyncio
async def test_client_call_tool_returns_content():
    client = make_mock_client("http://server1", ["tool_a"])
    mock_response = MagicMock()
    mock_response.content = "tool_output"
    client._session.call_tool = AsyncMock(return_value=mock_response)
    client.call_tool = MCPClient.call_tool.__get__(client)

    result = await client.call_tool("tool_a", {"key": "value"})
    assert result == "tool_output"
    client._session.call_tool.assert_called_once_with("tool_a", {"key": "value"})


def test_client_tools_property():
    client = make_mock_client("http://server1", ["tool_a", "tool_b"])
    assert client.tools == ["tool_a", "tool_b"]


# --- bus ---

@pytest.mark.asyncio
async def test_bus_start_connects_all_clients():
    client1 = make_mock_client("http://server1", ["tool_a"])
    client2 = make_mock_client("http://server2", ["tool_b"])

    bus = MCPBus.__new__(MCPBus)
    bus._clients = [client1, client2]
    bus._registry = MCPRegistry()

    await bus.start()

    client1.connect.assert_called_once()
    client2.connect.assert_called_once()


@pytest.mark.asyncio
async def test_bus_stop_disconnects_all_clients():
    client1 = make_mock_client("http://server1", ["tool_a"])
    client2 = make_mock_client("http://server2", ["tool_b"])

    bus = MCPBus.__new__(MCPBus)
    bus._clients = [client1, client2]
    bus._registry = MCPRegistry()

    await bus.stop()

    client1.disconnect.assert_called_once()
    client2.disconnect.assert_called_once()


@pytest.mark.asyncio
async def test_bus_call_routes_to_correct_client():
    client1 = make_mock_client("http://server1", ["tool_a"])
    client2 = make_mock_client("http://server2", ["tool_b"])

    bus = MCPBus.__new__(MCPBus)
    bus._clients = [client1, client2]
    bus._registry = MCPRegistry()
    bus._registry.register(client1)
    bus._registry.register(client2)

    await bus.call("tool_a", {"x": 1})
    client1.call_tool.assert_called_once_with("tool_a", {"x": 1})
    client2.call_tool.assert_not_called()


@pytest.mark.asyncio
async def test_bus_call_raises_for_unknown_tool():
    bus = MCPBus.__new__(MCPBus)
    bus._clients = []
    bus._registry = MCPRegistry()

    with pytest.raises(ToolNotFoundError):
        await bus.call("nonexistent", {})
