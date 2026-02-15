"""Tests for the OpenAPI parser."""

import json
import os
from pathlib import Path

import pytest

from src.config import load_config, resolve_env_vars
from src.parser import OpenAPIParser
from src.registry import APIRegistry

FIXTURES_DIR = Path(__file__).parent / "fixtures"
PETSTORE_SPEC = FIXTURES_DIR / "petstore.json"


class TestConfig:
    """Tests for configuration loading."""

    def test_resolve_env_vars_with_env(self):
        """Test resolving environment variables."""
        os.environ["TEST_API_KEY"] = "secret-key-123"
        result = resolve_env_vars("$TEST_API_KEY")
        assert result == "secret-key-123"
        del os.environ["TEST_API_KEY"]

    def test_resolve_env_vars_without_dollar(self):
        """Test that values without $ are returned as-is."""
        result = resolve_env_vars("plain-value")
        assert result == "plain-value"

    def test_resolve_env_vars_missing(self):
        """Test that missing env vars return empty string."""
        result = resolve_env_vars("$NONEXISTENT_VAR_12345")
        assert result == ""

    def test_resolve_env_vars_none(self):
        """Test that None is returned as None."""
        result = resolve_env_vars(None)
        assert result is None

    def test_load_config(self, tmp_path):
        """Test loading a config file."""
        config_file = tmp_path / "test_apis.json"
        config_file.write_text(
            json.dumps(
                {
                    "apis": [
                        {
                            "name": "test-api",
                            "spec_url": "http://example.com/openapi.json",
                            "base_url": "http://example.com",
                        }
                    ]
                }
            )
        )

        config = load_config(config_file)
        assert len(config.apis) == 1
        assert config.apis[0].name == "test-api"
        assert config.apis[0].auth.type == "none"  # default


class TestOpenAPIParser:
    """Tests for the OpenAPI parser."""

    @pytest.fixture
    def parser(self):
        return OpenAPIParser()

    @pytest.mark.asyncio
    async def test_parse_petstore_spec(self, parser):
        """Test parsing the Petstore spec."""
        if not PETSTORE_SPEC.exists():
            pytest.skip("Petstore spec not found")

        spec = await parser.parse(str(PETSTORE_SPEC))

        assert spec.title == "Swagger Petstore - OpenAPI 3.0"
        assert spec.version.startswith("1.0.")  # Version may change
        assert spec.description is not None

    @pytest.mark.asyncio
    async def test_endpoint_count(self, parser):
        """Test that correct number of endpoints are extracted."""
        if not PETSTORE_SPEC.exists():
            pytest.skip("Petstore spec not found")

        spec = await parser.parse(str(PETSTORE_SPEC))

        # Petstore has multiple endpoints across pet, store, user
        assert len(spec.endpoints) > 10

    @pytest.mark.asyncio
    async def test_parameters_parsed(self, parser):
        """Test that parameters are properly parsed."""
        if not PETSTORE_SPEC.exists():
            pytest.skip("Petstore spec not found")

        spec = await parser.parse(str(PETSTORE_SPEC))

        # Find GET /pet/{petId} endpoint
        pet_by_id = None
        for endpoint in spec.endpoints:
            if endpoint.path == "/pet/{petId}" and endpoint.method == "GET":
                pet_by_id = endpoint
                break

        assert pet_by_id is not None
        assert len(pet_by_id.parameters) > 0

        # Check petId parameter
        pet_id_param = next(
            (p for p in pet_by_id.parameters if p.name == "petId"), None
        )
        assert pet_id_param is not None
        assert pet_id_param.location == "path"
        assert pet_id_param.required is True

    @pytest.mark.asyncio
    async def test_ref_resolution(self, parser):
        """Test that $ref references are resolved."""
        if not PETSTORE_SPEC.exists():
            pytest.skip("Petstore spec not found")

        spec = await parser.parse(str(PETSTORE_SPEC))

        # Find POST /pet endpoint which has a Pet schema ref
        post_pet = None
        for endpoint in spec.endpoints:
            if endpoint.path == "/pet" and endpoint.method == "POST":
                post_pet = endpoint
                break

        assert post_pet is not None
        # Request body should be resolved, not a $ref
        assert post_pet.request_body_schema is not None
        # Should have actual properties, not just a $ref
        if "properties" in post_pet.request_body_schema:
            assert "name" in post_pet.request_body_schema["properties"]

    @pytest.mark.asyncio
    async def test_path_and_query_params(self, parser):
        """Test that both path and query parameters are captured."""
        if not PETSTORE_SPEC.exists():
            pytest.skip("Petstore spec not found")

        spec = await parser.parse(str(PETSTORE_SPEC))

        # Find GET /pet/findByStatus which has query params
        find_by_status = None
        for endpoint in spec.endpoints:
            if endpoint.path == "/pet/findByStatus" and endpoint.method == "GET":
                find_by_status = endpoint
                break

        assert find_by_status is not None
        assert len(find_by_status.parameters) > 0

        status_param = next(
            (p for p in find_by_status.parameters if p.name == "status"), None
        )
        assert status_param is not None
        assert status_param.location == "query"

    @pytest.mark.asyncio
    async def test_operation_id_extracted(self, parser):
        """Test that operationId is extracted."""
        if not PETSTORE_SPEC.exists():
            pytest.skip("Petstore spec not found")

        spec = await parser.parse(str(PETSTORE_SPEC))

        # Most endpoints should have operationId
        endpoints_with_op_id = [e for e in spec.endpoints if e.operation_id]
        assert len(endpoints_with_op_id) > 5

    @pytest.mark.asyncio
    async def test_tags_extracted(self, parser):
        """Test that tags are extracted."""
        if not PETSTORE_SPEC.exists():
            pytest.skip("Petstore spec not found")

        spec = await parser.parse(str(PETSTORE_SPEC))

        # Find endpoints with pet tag
        pet_endpoints = [e for e in spec.endpoints if "pet" in e.tags]
        assert len(pet_endpoints) > 0


class TestAPIRegistry:
    """Tests for the API registry."""

    @pytest.mark.asyncio
    async def test_register_local_spec(self):
        """Test registering an API with a local spec file."""
        if not PETSTORE_SPEC.exists():
            pytest.skip("Petstore spec not found")

        from src.config import APIConfig

        registry = APIRegistry()
        config = APIConfig(
            name="test-petstore",
            spec_url=str(PETSTORE_SPEC),
            base_url="https://petstore3.swagger.io/api/v3",
        )

        await registry.register_api(config)

        assert "test-petstore" in registry.get_api_names()
        assert registry.get_api("test-petstore") is not None

        spec = registry.get_spec("test-petstore")
        assert spec is not None
        assert len(spec.endpoints) > 10

    @pytest.mark.asyncio
    async def test_list_apis(self):
        """Test listing registered APIs."""
        if not PETSTORE_SPEC.exists():
            pytest.skip("Petstore spec not found")

        from src.config import APIConfig

        registry = APIRegistry()
        config = APIConfig(
            name="test-petstore",
            spec_url=str(PETSTORE_SPEC),
            base_url="https://petstore3.swagger.io/api/v3",
        )

        await registry.register_api(config)

        apis = registry.list_apis()
        assert len(apis) == 1
        assert apis[0]["name"] == "test-petstore"
        assert apis[0]["endpoint_count"] > 10
        assert apis[0]["auth_type"] == "none"

    @pytest.mark.asyncio
    async def test_get_endpoints(self):
        """Test getting endpoints for an API."""
        if not PETSTORE_SPEC.exists():
            pytest.skip("Petstore spec not found")

        from src.config import APIConfig

        registry = APIRegistry()
        config = APIConfig(
            name="test-petstore",
            spec_url=str(PETSTORE_SPEC),
            base_url="https://petstore3.swagger.io/api/v3",
        )

        await registry.register_api(config)

        endpoints = registry.get_endpoints("test-petstore")
        assert len(endpoints) > 10

        # Check various endpoint methods exist
        methods = {e.method for e in endpoints}
        assert "GET" in methods
        assert "POST" in methods
        assert "PUT" in methods
        assert "DELETE" in methods
