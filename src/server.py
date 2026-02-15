"""MCP server entry point with 4 tools for OpenAPI bridge."""

import argparse
import asyncio
import logging
import os
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from .config import load_config
from .executor import AsyncAPIExecutor, BatchExecutor
from .guardrails import Guardrails
from .parser import Endpoint
from .registry import APIRegistry
from .search.base import SearchProvider
from .search.fuzzy import FuzzySearchProvider

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize the MCP server
mcp = FastMCP("openapi-bridge")

# Global instances (initialized on startup)
registry: APIRegistry | None = None
search_provider: SearchProvider | None = None
guardrails: Guardrails | None = None
executors: dict[str, AsyncAPIExecutor] = {}

# Search provider type (can be set via --search-provider flag or env var)
_search_provider_type: str = os.environ.get("SEARCH_PROVIDER", "fuzzy")


def get_config_path() -> Path:
    """Get the path to the apis.json config file."""
    # Look in several locations
    candidates = [
        Path("config/apis.json"),
        Path(__file__).parent.parent / "config" / "apis.json",
        Path.home() / ".config" / "openapi-mcp-bridge" / "apis.json",
    ]
    for path in candidates:
        if path.exists():
            return path
    return candidates[0]  # Default to first option


def create_search_provider(provider_type: str) -> SearchProvider:
    """Create a search provider based on the type."""
    if provider_type == "embedding":
        from .search.embedding import EmbeddingSearchProvider
        logger.info("Using embedding search provider (sentence-transformers)")
        return EmbeddingSearchProvider(confidence_threshold=0.4)
    else:
        logger.info("Using fuzzy search provider (thefuzz)")
        return FuzzySearchProvider(confidence_threshold=0.4)


async def initialize():
    """Initialize the registry and load all APIs."""
    global registry, search_provider, guardrails, executors

    registry = APIRegistry()
    search_provider = create_search_provider(_search_provider_type)
    guardrails = Guardrails()

    config_path = get_config_path()
    if config_path.exists():
        logger.info(f"Loading config from {config_path}")
        await registry.load_config(config_path)

        # Create executors for each API
        for api_name in registry.get_api_names():
            api_config = registry.get_api(api_name)
            if api_config:
                executors[api_name] = AsyncAPIExecutor(api_config)
    else:
        logger.warning(f"Config file not found: {config_path}")


def endpoint_to_dict(endpoint: Endpoint) -> dict[str, Any]:
    """Convert an Endpoint to a serializable dict."""
    return {
        "path": endpoint.path,
        "method": endpoint.method,
        "summary": endpoint.summary,
        "description": endpoint.description,
        "operation_id": endpoint.operation_id,
        "tags": endpoint.tags,
        "parameters": [
            {
                "name": p.name,
                "location": p.location,
                "required": p.required,
                "description": p.description,
                "schema": p.param_schema,
            }
            for p in endpoint.parameters
        ],
        "request_body_schema": endpoint.request_body_schema,
        "response_schema": endpoint.response_schema,
    }


@mcp.tool()
async def list_apis() -> list[dict[str, Any]]:
    """
    List all registered OpenAPI/Swagger APIs available for querying.

    Returns a list of APIs with their name, base_url, description,
    authentication type, and number of endpoints.
    """
    if registry is None:
        await initialize()

    return registry.list_apis()


@mcp.tool()
async def search_endpoints(
    api: str,
    query: str,
    limit: int = 5,
) -> dict[str, Any]:
    """
    Search for API endpoints by natural language description.

    Returns matching endpoints with full details including parameters,
    request body schema, and response schema, along with similarity scores.

    Args:
        api: Name of the API to search (use list_apis to see available APIs)
        query: Natural language description of what you're looking for
        limit: Maximum number of results to return (default: 5)
    """
    if registry is None:
        await initialize()

    # Check if API exists
    if api not in registry.get_api_names():
        available = registry.get_api_names()
        return {
            "error": f"API '{api}' not found",
            "available_apis": available,
            "hint": "Use list_apis() to see all available APIs",
        }

    # Get endpoints and search
    endpoints = registry.get_endpoints(api)
    results = search_provider.search(query, endpoints, limit=limit)

    return {
        "api": api,
        "query": query,
        "results": [
            {
                "endpoint": endpoint_to_dict(r.endpoint),
                "similarity_score": r.similarity_score,
                "low_confidence": r.low_confidence,
            }
            for r in results
        ],
        "total_results": len(results),
    }


@mcp.tool()
async def execute_endpoint(
    api: str,
    path: str,
    method: str,
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    limit: int = 20,
    offset: int = 0,
    confirmed: bool = False,
) -> dict[str, Any]:
    """
    Execute an API endpoint.

    For destructive operations (DELETE, PUT, PATCH), set confirmed=true
    after user approval.

    Args:
        api: Name of the API
        path: Endpoint path (e.g., "/pets/{petId}")
        method: HTTP method (GET, POST, PUT, DELETE, PATCH)
        params: Query and path parameters as a dict
        body: Request body for POST/PUT/PATCH
        headers: Additional headers
        limit: Response truncation limit (default: 20)
        offset: Pagination offset (default: 0)
        confirmed: Required true for destructive operations (DELETE, PUT, PATCH)
    """
    if registry is None:
        await initialize()

    # Check if API exists
    if api not in executors:
        available = registry.get_api_names()
        return {
            "error": f"API '{api}' not found",
            "available_apis": available,
        }

    # Check guardrails
    check = guardrails.check_operation(method, path, confirmed)
    if not check.allowed:
        return {
            "status_code": 0,
            "data": None,
            "destructive_warning": check.warning,
            "hint": "Set confirmed=true to proceed with this destructive operation",
        }

    # Execute the request
    executor = executors[api]
    result = await executor.execute(
        path=path,
        method=method,
        params=params,
        body=body,
        headers=headers,
        limit=limit,
        offset=offset,
    )

    return {
        "status_code": result.status_code,
        "data": result.data,
        "total_count": result.total_count,
        "truncated": result.truncated,
        "auth_error": result.auth_error,
        "error": result.error,
    }


@mcp.tool()
async def batch_execute(
    api: str,
    requests: list[dict[str, Any]],
    parallel: bool = True,
    confirmed: bool = False,
) -> dict[str, Any]:
    """
    Execute multiple API endpoints in parallel or sequentially.

    Always requires user confirmation before execution since batch
    operations are inherently risky.

    Args:
        api: Name of the API
        requests: List of request configs, each with:
            - path: API path
            - method: HTTP method
            - params: Optional parameters dict
            - body: Optional request body
            - headers: Optional headers
        parallel: Execute in parallel if true (default: true)
        confirmed: Required true to proceed with batch execution
    """
    if registry is None:
        await initialize()

    # Check if API exists
    if api not in executors:
        available = registry.get_api_names()
        return {
            "error": f"API '{api}' not found",
            "available_apis": available,
        }

    # Always require confirmation for batch operations
    if not confirmed:
        # Build summary of what will be executed
        summary = []
        for req in requests:
            summary.append(f"{req.get('method', 'GET')} {req.get('path', '/')}")

        return {
            "confirmation_required": True,
            "operations": summary,
            "total_operations": len(requests),
            "hint": "Set confirmed=true to execute these operations",
        }

    # Execute batch
    executor = executors[api]
    batch = BatchExecutor(executor, concurrency=5)
    result = await batch.execute_batch(requests, parallel=parallel)

    return {
        "results": [
            {
                "status_code": r.status_code,
                "data": r.data,
                "error": r.error,
            }
            for r in result.results
        ],
        "summary": result.summary,
    }


def main():
    """Run the MCP server."""
    global _search_provider_type

    parser = argparse.ArgumentParser(description="OpenAPI MCP Bridge Server")
    parser.add_argument(
        "--search-provider",
        choices=["fuzzy", "embedding"],
        default=os.environ.get("SEARCH_PROVIDER", "fuzzy"),
        help="Search provider to use: 'fuzzy' (default) or 'embedding' (requires sentence-transformers)",
    )
    args = parser.parse_args()

    _search_provider_type = args.search_provider

    # Initialize before running
    asyncio.get_event_loop().run_until_complete(initialize())
    mcp.run()


if __name__ == "__main__":
    main()
