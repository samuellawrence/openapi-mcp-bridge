"""API registry for managing registered OpenAPI specifications."""

import logging
from pathlib import Path

from .config import APIConfig, Config, load_config
from .parser import Endpoint, OpenAPIParser, ParsedSpec

logger = logging.getLogger(__name__)


class APIRegistry:
    """Registry for managing multiple API specifications."""

    def __init__(self):
        self._apis: dict[str, APIConfig] = {}
        self._specs: dict[str, ParsedSpec] = {}
        self._parser = OpenAPIParser()

    async def load_config(self, config_path: str | Path) -> None:
        """
        Load API configurations from a JSON file and parse all specs.

        Args:
            config_path: Path to the apis.json configuration file.
        """
        config = load_config(config_path)

        for api_config in config.apis:
            await self.register_api(api_config)

    async def register_api(self, config: APIConfig) -> None:
        """
        Register an API and parse its OpenAPI specification.

        Args:
            config: API configuration including spec URL.
        """
        self._apis[config.name] = config

        try:
            spec = await self._parser.parse(config.spec_url)
            self._specs[config.name] = spec
            logger.info(
                f"Registered API '{config.name}' with {len(spec.endpoints)} endpoints"
            )
        except Exception as e:
            logger.error(f"Failed to parse spec for '{config.name}': {e}")
            # Store empty spec so we can still list the API
            self._specs[config.name] = ParsedSpec(
                title=config.name,
                version="unknown",
                description=f"Failed to load spec: {e}",
                endpoints=[],
            )

    def list_apis(self) -> list[dict]:
        """
        List all registered APIs with their metadata.

        Returns:
            List of dicts with name, base_url, description, auth_type, endpoint_count.
        """
        result = []
        for name, config in self._apis.items():
            spec = self._specs.get(name)
            result.append(
                {
                    "name": name,
                    "base_url": config.base_url,
                    "description": spec.description if spec else None,
                    "auth_type": config.auth.type,
                    "endpoint_count": len(spec.endpoints) if spec else 0,
                }
            )
        return result

    def get_api(self, name: str) -> APIConfig | None:
        """
        Get the configuration for a specific API.

        Args:
            name: The API name.

        Returns:
            APIConfig if found, None otherwise.
        """
        return self._apis.get(name)

    def get_spec(self, name: str) -> ParsedSpec | None:
        """
        Get the parsed specification for a specific API.

        Args:
            name: The API name.

        Returns:
            ParsedSpec if found, None otherwise.
        """
        return self._specs.get(name)

    def get_endpoints(self, api_name: str) -> list[Endpoint]:
        """
        Get all endpoints for a specific API.

        Args:
            api_name: The API name.

        Returns:
            List of Endpoint objects, empty list if API not found.
        """
        spec = self._specs.get(api_name)
        if spec:
            return spec.endpoints
        return []

    def get_api_names(self) -> list[str]:
        """Get list of all registered API names."""
        return list(self._apis.keys())
