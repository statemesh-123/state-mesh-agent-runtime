import sys
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock


from state_mesh.state.memory import InMemoryBackend


# --- InMemoryBackend ---

@pytest.mark.asyncio
async def test_memory_save_and_load():
    backend = InMemoryBackend()
    await backend.save("run-1", {"value": 42})
    result = await backend.load("run-1")
    assert result == {"value": 42}


@pytest.mark.asyncio
async def test_memory_load_returns_none_for_unknown():
    backend = InMemoryBackend()
    result = await backend.load("nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_memory_delete_removes_key():
    backend = InMemoryBackend()
    await backend.save("run-1", {"value": 1})
    await backend.delete("run-1")
    assert await backend.load("run-1") is None


@pytest.mark.asyncio
async def test_memory_delete_nonexistent_does_not_raise():
    backend = InMemoryBackend()
    await backend.delete("ghost")  # should not raise


# --- RedisStateBackend ---

def make_redis_backend():
    from state_mesh.state.redis_backend import RedisStateBackend  

    mock_client = MagicMock()
    mock_client.set = AsyncMock()
    mock_client.get = AsyncMock()
    mock_client.delete = AsyncMock()
    mock_client.aclose = AsyncMock()

    backend = RedisStateBackend.__new__(RedisStateBackend)
    backend.url = "redis://localhost:6379"
    backend.ttl = 3600
    backend._client = mock_client
    return backend, mock_client


@pytest.mark.asyncio
async def test_redis_save_calls_set_with_ttl():
    backend, mock_client = make_redis_backend()
    mock_client.set = AsyncMock()

    class State:
        def model_dump_json(self): return '{"value": 1}'

    await backend.save("run-1", State())
    mock_client.set.assert_called_once_with("run-1", '{"value": 1}', ex=3600)


@pytest.mark.asyncio
async def test_redis_save_plain_dict():
    backend, mock_client = make_redis_backend()
    mock_client.set = AsyncMock()

    await backend.save("run-1", {"value": 99})
    mock_client.set.assert_called_once_with("run-1", '{"value": 99}', ex=3600)


@pytest.mark.asyncio
async def test_redis_load_returns_parsed_json():
    backend, mock_client = make_redis_backend()
    mock_client.get = AsyncMock(return_value=b'{"value": 42}')

    result = await backend.load("run-1")
    assert result == {"value": 42}


@pytest.mark.asyncio
async def test_redis_load_returns_none_when_missing():
    backend, mock_client = make_redis_backend()
    mock_client.get = AsyncMock(return_value=None)

    result = await backend.load("run-1")
    assert result is None


@pytest.mark.asyncio
async def test_redis_delete_calls_client_delete():
    backend, mock_client = make_redis_backend()
    mock_client.delete = AsyncMock()

    await backend.delete("run-1")
    mock_client.delete.assert_called_once_with("run-1")
