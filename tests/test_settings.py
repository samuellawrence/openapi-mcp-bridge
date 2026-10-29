"""Tests for per-API settings: page size, batch size, rate limit, confirmation."""

import time

import pytest

from src import server
from src.config import APIConfig, APISettings
from src.executor import AsyncAPIExecutor, ExecutionResult, RateLimiter
from src.guardrails import Guardrails
from src.registry import APIRegistry
from src.search.fuzzy import FuzzySearchProvider


class TestRateLimiter:
    """Tests for the rate limiter."""

    @pytest.mark.asyncio
    async def test_spaces_requests(self):
        """Test that requests beyond the first wait for their slot."""
        limiter = RateLimiter(rate=10)
        start = time.monotonic()
        for _ in range(4):
            await limiter.acquire()
        # 4 requests at 10/s: the first is immediate, the rest 0.1s apart
        assert time.monotonic() - start >= 0.28

    @pytest.mark.asyncio
    async def test_first_request_is_immediate(self):
        """Test that a single request does not wait."""
        limiter = RateLimiter(rate=1)
        start = time.monotonic()
        await limiter.acquire()
        assert time.monotonic() - start < 0.05


@pytest.fixture
def api(monkeypatch):
    """Register one API with custom settings directly on the server globals."""

    def register(**settings) -> AsyncAPIExecutor:
        config = APIConfig(
            name="test",
            spec_url="http://example.com/openapi.json",
            base_url="http://localhost:59999",  # Non-existent
            settings=APISettings(rate_limit_per_second=100, **settings),
        )
        executor = AsyncAPIExecutor(config)
        monkeypatch.setattr(server, "registry", APIRegistry())
        monkeypatch.setattr(server, "search_provider", FuzzySearchProvider())
        monkeypatch.setattr(server, "guardrails", Guardrails())
        monkeypatch.setattr(server, "executors", {"test": executor})
        return executor

    return register


class TestServerSettings:
    """Tests that the server tools honor per-API settings."""

    @pytest.mark.asyncio
    async def test_default_page_size_used_when_no_limit(self, api, monkeypatch):
        """Test that execute_endpoint falls back to default_page_size."""
        executor = api(default_page_size=7)
        seen = {}

        async def fake_execute(**kwargs):
            seen.update(kwargs)
            return ExecutionResult(status_code=200, data=[])

        monkeypatch.setattr(executor, "execute", fake_execute)

        await server.execute_endpoint(api="test", path="/pets", method="GET")
        assert seen["limit"] == 7

        await server.execute_endpoint(api="test", path="/pets", method="GET", limit=3)
        assert seen["limit"] == 3

    @pytest.mark.asyncio
    async def test_batch_over_max_size_rejected(self, api):
        """Test that batch_execute rejects batches above max_batch_size."""
        api(max_batch_size=2)
        requests = [{"path": f"/pets/{i}", "method": "GET"} for i in range(3)]

        result = await server.batch_execute(api="test", requests=requests, confirmed=True)

        assert "error" in result
        assert "limit for 'test' is 2" in result["error"]

    @pytest.mark.asyncio
    async def test_destructive_blocked_by_default(self, api):
        """Test that DELETE needs confirmation when confirm_destructive is on."""
        api()

        result = await server.execute_endpoint(api="test", path="/pets/1", method="DELETE")

        assert result["destructive_warning"] is not None

    @pytest.mark.asyncio
    async def test_confirm_destructive_off_skips_guardrail(self, api):
        """Test that DELETE runs unconfirmed when confirm_destructive is off."""
        api(confirm_destructive=False)

        result = await server.execute_endpoint(api="test", path="/pets/1", method="DELETE")

        assert "destructive_warning" not in result
        assert "Connection error" in result["error"]
