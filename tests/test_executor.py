"""Tests for the HTTP executor."""

import pytest

from src.config import APIConfig, AuthConfig
from src.executor import AsyncAPIExecutor, BatchExecutor
from src.guardrails import Guardrails


class TestGuardrails:
    """Tests for guardrails."""

    def test_get_is_safe(self):
        """Test that GET is not destructive."""
        guardrails = Guardrails()
        assert not guardrails.is_destructive("GET")
        assert not guardrails.is_destructive("get")

    def test_delete_is_destructive(self):
        """Test that DELETE is destructive."""
        guardrails = Guardrails()
        assert guardrails.is_destructive("DELETE")
        assert guardrails.is_destructive("delete")

    def test_put_is_destructive(self):
        """Test that PUT is destructive."""
        guardrails = Guardrails()
        assert guardrails.is_destructive("PUT")

    def test_patch_is_destructive(self):
        """Test that PATCH is destructive."""
        guardrails = Guardrails()
        assert guardrails.is_destructive("PATCH")

    def test_post_is_safe_by_default(self):
        """Test that POST is not destructive by default."""
        guardrails = Guardrails()
        assert not guardrails.is_destructive("POST")

    def test_custom_destructive_methods(self):
        """Test custom destructive methods list."""
        guardrails = Guardrails(destructive_methods=["DELETE", "POST"])
        assert guardrails.is_destructive("DELETE")
        assert guardrails.is_destructive("POST")
        assert not guardrails.is_destructive("PUT")

    def test_check_safe_operation(self):
        """Test checking a safe operation."""
        guardrails = Guardrails()
        result = guardrails.check_operation("GET", "/pets")
        assert result.allowed is True
        assert result.warning is None

    def test_check_destructive_not_confirmed(self):
        """Test destructive operation without confirmation."""
        guardrails = Guardrails()
        result = guardrails.check_operation("DELETE", "/pets/1", confirmed=False)
        assert result.allowed is False
        assert result.warning is not None
        assert "DELETE" in result.warning
        assert "confirmed=true" in result.warning

    def test_check_destructive_confirmed(self):
        """Test destructive operation with confirmation."""
        guardrails = Guardrails()
        result = guardrails.check_operation("DELETE", "/pets/1", confirmed=True)
        assert result.allowed is True
        assert result.warning is None


class TestAsyncAPIExecutor:
    """Tests for the API executor."""

    @pytest.fixture
    def executor(self):
        config = APIConfig(
            name="test",
            spec_url="http://example.com/openapi.json",
            base_url="http://localhost:8000",
            auth=AuthConfig(
                type="api_key",
                token="test-key",
                header_name="X-API-Key",
                api_key_in="header",
            ),
        )
        return AsyncAPIExecutor(config)

    def test_build_url_simple(self, executor):
        """Test URL building without path params."""
        url = executor._build_url("/pets", {})
        assert url == "http://localhost:8000/pets"

    def test_build_url_with_path_param(self, executor):
        """Test URL building with path parameters."""
        url = executor._build_url("/pets/{petId}", {"petId": 123})
        assert url == "http://localhost:8000/pets/123"

    def test_build_url_multiple_path_params(self, executor):
        """Test URL building with multiple path parameters."""
        url = executor._build_url(
            "/stores/{storeId}/pets/{petId}",
            {"storeId": "abc", "petId": 456},
        )
        assert url == "http://localhost:8000/stores/abc/pets/456"

    def test_extract_query_params(self, executor):
        """Test extracting query parameters."""
        params = {"petId": 123, "status": "available", "limit": 10}
        query = executor._extract_query_params("/pets/{petId}", params)

        # petId should be excluded (it's a path param)
        assert "petId" not in query
        assert query["status"] == "available"
        assert query["limit"] == 10

    def test_build_headers_api_key(self, executor):
        """Test header building for API key auth."""
        headers = executor._build_headers()
        assert headers["X-API-Key"] == "test-key"
        assert headers["Content-Type"] == "application/json"

    def test_build_headers_bearer(self):
        """Test header building for bearer auth."""
        config = APIConfig(
            name="test",
            spec_url="http://example.com/openapi.json",
            base_url="http://localhost:8000",
            auth=AuthConfig(type="bearer", token="my-token"),
        )
        executor = AsyncAPIExecutor(config)
        headers = executor._build_headers()
        assert headers["Authorization"] == "Bearer my-token"

    def test_build_headers_basic(self):
        """Test header building for basic auth."""
        config = APIConfig(
            name="test",
            spec_url="http://example.com/openapi.json",
            base_url="http://localhost:8000",
            auth=AuthConfig(type="basic", token="user:pass"),
        )
        executor = AsyncAPIExecutor(config)
        headers = executor._build_headers()
        # base64 of "user:pass" = "dXNlcjpwYXNz"
        assert headers["Authorization"] == "Basic dXNlcjpwYXNz"

    @pytest.mark.asyncio
    async def test_execute_connection_error(self, executor):
        """Test handling connection errors."""
        # Use a non-existent server
        executor.base_url = "http://localhost:59999"
        result = await executor.execute("/pets", "GET")

        assert result.status_code == 0
        assert result.error is not None
        assert "Connection error" in result.error


class TestBatchExecutor:
    """Tests for batch execution."""

    @pytest.fixture
    def executor(self):
        config = APIConfig(
            name="test",
            spec_url="http://example.com/openapi.json",
            base_url="http://localhost:59999",  # Non-existent
        )
        return AsyncAPIExecutor(config)

    @pytest.mark.asyncio
    async def test_batch_execution_summary(self, executor):
        """Test batch execution returns proper summary."""
        batch = BatchExecutor(executor, concurrency=2)

        requests = [
            {"path": "/pets/1", "method": "GET"},
            {"path": "/pets/2", "method": "GET"},
            {"path": "/pets/3", "method": "GET"},
        ]

        result = await batch.execute_batch(requests)

        assert len(result.results) == 3
        assert result.summary["total"] == 3
        # All should fail since server doesn't exist
        assert result.summary["failed"] == 3
        assert result.summary["succeeded"] == 0
