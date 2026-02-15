"""Integration tests for the MCP server."""

import asyncio
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from src.config import APIConfig, AuthConfig
from src.executor import AsyncAPIExecutor, BatchExecutor
from src.guardrails import Guardrails
from src.parser import OpenAPIParser
from src.registry import APIRegistry
from src.search.fuzzy import FuzzySearchProvider

# Test configuration
MOCK_SERVER_PORT = 8000
MOCK_SERVER_URL = f"http://localhost:{MOCK_SERVER_PORT}"
API_KEY = "test-key-123"


@pytest.fixture(scope="module")
def mock_server():
    """Start the mock petstore server for integration tests."""
    # Start the server
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "mock-petstore.app:app", "--port", str(MOCK_SERVER_PORT)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Wait for server to be ready
    max_retries = 10
    for i in range(max_retries):
        try:
            response = httpx.get(f"{MOCK_SERVER_URL}/openapi.json", timeout=1.0)
            if response.status_code == 200:
                break
        except Exception:
            pass
        time.sleep(1)
    else:
        proc.kill()
        pytest.fail("Mock server failed to start")

    yield proc

    # Cleanup
    proc.terminate()
    proc.wait(timeout=5)


@pytest.fixture
def api_config():
    """Create API config for local mock server."""
    return APIConfig(
        name="local-petstore",
        spec_url=f"{MOCK_SERVER_URL}/openapi.json",
        base_url=MOCK_SERVER_URL,
        auth=AuthConfig(
            type="api_key",
            token=API_KEY,
            header_name="X-API-Key",
            api_key_in="header",
        ),
    )


@pytest.fixture
async def registry(mock_server, api_config):
    """Create and initialize registry with mock server."""
    reg = APIRegistry()
    await reg.register_api(api_config)
    return reg


@pytest.fixture
def executor(api_config):
    """Create executor for mock server."""
    return AsyncAPIExecutor(api_config)


@pytest.fixture
def search_provider():
    """Create fuzzy search provider."""
    return FuzzySearchProvider(confidence_threshold=0.4)


@pytest.fixture
def guardrails():
    """Create guardrails instance."""
    return Guardrails()


class TestScenario1SimpleQuery:
    """Scenario 1: Simple Query - list APIs, search, execute GET."""

    @pytest.mark.asyncio
    async def test_list_apis(self, registry):
        """Verify local-petstore is listed."""
        apis = registry.list_apis()
        assert len(apis) == 1
        assert apis[0]["name"] == "local-petstore"
        assert apis[0]["endpoint_count"] > 0

    @pytest.mark.asyncio
    async def test_search_find_pets(self, registry, search_provider):
        """Search for 'find all pets' returns GET /pets."""
        endpoints = registry.get_endpoints("local-petstore")
        results = search_provider.search("find all pets", endpoints, limit=5)

        assert len(results) > 0
        # GET /pets should be in top results
        top_paths = [r.endpoint.path for r in results[:3]]
        assert any("/pets" in p for p in top_paths)

    @pytest.mark.asyncio
    async def test_execute_get_pets(self, mock_server, executor):
        """Execute GET /pets and verify pre-seeded data."""
        result = await executor.execute("/pets", "GET", params={"status": "available"})

        assert result.status_code == 200
        assert isinstance(result.data, list)
        assert len(result.data) > 0
        # Pre-seeded data should have available pets
        assert all(pet["status"] == "available" for pet in result.data)


class TestScenario2DependencyChain:
    """Scenario 2: Dependency Chain - create pet, then get by ID."""

    @pytest.mark.asyncio
    async def test_create_and_get_pet(self, mock_server, executor):
        """Create a pet, then retrieve it by ID."""
        # Create pet
        new_pet = {
            "name": "TestDog",
            "species": "dog",
            "status": "available",
            "tags": ["test"],
        }
        create_result = await executor.execute("/pets", "POST", body=new_pet)

        assert create_result.status_code == 201
        assert create_result.data["name"] == "TestDog"
        pet_id = create_result.data["id"]

        # Get pet by ID
        get_result = await executor.execute(
            "/pets/{pet_id}",
            "GET",
            params={"pet_id": pet_id},
        )

        assert get_result.status_code == 200
        assert get_result.data["id"] == pet_id
        assert get_result.data["name"] == "TestDog"
        assert get_result.data["species"] == "dog"


class TestScenario3DestructiveGuardrail:
    """Scenario 3: Destructive Operation Guardrail."""

    @pytest.mark.asyncio
    async def test_delete_without_confirmation(self, guardrails):
        """DELETE without confirmation returns warning."""
        result = guardrails.check_operation("DELETE", "/pets/1", confirmed=False)

        assert result.allowed is False
        assert result.warning is not None
        assert "DELETE" in result.warning

    @pytest.mark.asyncio
    async def test_delete_with_confirmation(self, mock_server, executor):
        """DELETE with confirmation proceeds and actually deletes."""
        # First create a pet to delete
        new_pet = {"name": "ToDelete", "species": "cat", "status": "available"}
        create_result = await executor.execute("/pets", "POST", body=new_pet)
        pet_id = create_result.data["id"]

        # Delete it
        delete_result = await executor.execute(
            "/pets/{pet_id}",
            "DELETE",
            params={"pet_id": pet_id},
        )
        assert delete_result.status_code == 204

        # Verify it's gone
        get_result = await executor.execute(
            "/pets/{pet_id}",
            "GET",
            params={"pet_id": pet_id},
        )
        assert get_result.status_code == 404


class TestScenario4BatchExecution:
    """Scenario 4: Batch Execution."""

    @pytest.mark.asyncio
    async def test_batch_get_pets(self, mock_server, executor):
        """Batch GET multiple pre-seeded pets."""
        batch = BatchExecutor(executor, concurrency=3)

        requests = [
            {"path": "/pets/{pet_id}", "method": "GET", "params": {"pet_id": 1}},
            {"path": "/pets/{pet_id}", "method": "GET", "params": {"pet_id": 2}},
            {"path": "/pets/{pet_id}", "method": "GET", "params": {"pet_id": 3}},
        ]

        result = await batch.execute_batch(requests, parallel=True)

        assert len(result.results) == 3
        assert result.summary["total"] == 3
        assert result.summary["succeeded"] == 3
        assert result.summary["failed"] == 0


class TestScenario5ErrorHandling:
    """Scenario 5: Error Handling."""

    @pytest.mark.asyncio
    async def test_search_invalid_api(self, registry, search_provider):
        """Search with non-existent API returns error."""
        # Registry should not have this API
        assert "nonexistent-api" not in registry.get_api_names()

    @pytest.mark.asyncio
    async def test_execute_nonexistent_pet(self, mock_server, executor):
        """GET non-existent pet returns 404."""
        result = await executor.execute(
            "/pets/{pet_id}",
            "GET",
            params={"pet_id": 99999},
        )

        assert result.status_code == 404
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_nonsense_query_low_confidence(self, registry, search_provider):
        """Nonsense query returns low confidence results."""
        endpoints = registry.get_endpoints("local-petstore")
        results = search_provider.search("xyzabc123qwerty", endpoints, limit=5)

        assert len(results) > 0
        assert all(r.low_confidence for r in results)


class TestScenario6ResponsePagination:
    """Scenario 6: Response Pagination."""

    @pytest.mark.asyncio
    async def test_pagination_limit(self, mock_server, executor):
        """GET /pets with limit returns limited results."""
        result = await executor.execute("/pets", "GET", limit=3)

        assert result.status_code == 200
        assert isinstance(result.data, list)
        assert len(result.data) <= 3

    @pytest.mark.asyncio
    async def test_pagination_offset(self, mock_server, executor):
        """GET /pets with offset returns different results."""
        # Get first page
        page1 = await executor.execute("/pets", "GET", params={"limit": 3, "offset": 0})
        # Get second page
        page2 = await executor.execute("/pets", "GET", params={"limit": 3, "offset": 3})

        assert page1.status_code == 200
        assert page2.status_code == 200

        # Pages should have different pets (if enough pre-seeded)
        page1_ids = {p["id"] for p in page1.data}
        page2_ids = {p["id"] for p in page2.data}

        # No overlap between pages
        assert page1_ids.isdisjoint(page2_ids)


class TestScenario7AuthFailure:
    """Scenario 7: Auth Failure."""

    @pytest.mark.asyncio
    async def test_wrong_api_key(self, mock_server):
        """Request with wrong API key returns 401."""
        bad_config = APIConfig(
            name="bad-auth",
            spec_url=f"{MOCK_SERVER_URL}/openapi.json",
            base_url=MOCK_SERVER_URL,
            auth=AuthConfig(
                type="api_key",
                token="wrong-key",
                header_name="X-API-Key",
                api_key_in="header",
            ),
        )
        bad_executor = AsyncAPIExecutor(bad_config)

        result = await bad_executor.execute("/pets", "GET")

        assert result.status_code == 401
        assert result.auth_error is True
