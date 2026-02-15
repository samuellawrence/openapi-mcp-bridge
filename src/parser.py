"""OpenAPI specification parser."""

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import yaml
from pydantic import BaseModel


class Parameter(BaseModel):
    """Represents an API parameter."""

    name: str
    location: str  # "path", "query", "header", "cookie"
    required: bool = False
    description: str | None = None
    param_schema: dict[str, Any] | None = None  # renamed from 'schema' to avoid shadowing


class Endpoint(BaseModel):
    """Represents a parsed API endpoint."""

    path: str
    method: str
    summary: str | None = None
    description: str | None = None
    operation_id: str | None = None
    tags: list[str] = []
    parameters: list[Parameter] = []
    request_body_schema: dict[str, Any] | None = None
    response_schema: dict[str, Any] | None = None
    security: list[dict[str, list[str]]] = []


class ParsedSpec(BaseModel):
    """Represents a fully parsed OpenAPI specification."""

    title: str
    version: str
    description: str | None = None
    endpoints: list[Endpoint] = []


class OpenAPIParser:
    """Parser for OpenAPI 3.x and Swagger 2.0 specifications."""

    HTTP_METHODS = {"get", "post", "put", "delete", "patch", "head", "options", "trace"}

    def __init__(self):
        self._spec: dict[str, Any] = {}
        self._components: dict[str, Any] = {}

    async def parse(self, spec_url: str) -> ParsedSpec:
        """
        Parse an OpenAPI specification from a URL or file path.

        Args:
            spec_url: URL or local file path to the OpenAPI spec.

        Returns:
            ParsedSpec with all endpoints extracted.
        """
        raw_spec = await self._fetch_spec(spec_url)
        self._spec = raw_spec

        # Store components/definitions for $ref resolution
        self._components = raw_spec.get("components", {}).get("schemas", {})
        # Swagger 2.0 uses "definitions" instead
        if not self._components:
            self._components = raw_spec.get("definitions", {})

        # Extract info
        info = raw_spec.get("info", {})
        title = info.get("title", "Unknown API")
        version = info.get("version", "1.0.0")
        description = info.get("description")

        # Extract endpoints
        endpoints = self._extract_endpoints(raw_spec)

        return ParsedSpec(
            title=title,
            version=version,
            description=description,
            endpoints=endpoints,
        )

    async def _fetch_spec(self, spec_url: str) -> dict[str, Any]:
        """Fetch and parse the spec from URL or file."""
        parsed = urlparse(spec_url)

        if parsed.scheme in ("http", "https"):
            # Remote URL
            async with httpx.AsyncClient() as client:
                response = await client.get(spec_url)
                response.raise_for_status()
                content = response.text
        else:
            # Local file
            path = Path(spec_url)
            content = path.read_text()

        # Parse as JSON or YAML
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return yaml.safe_load(content)

    def _extract_endpoints(self, spec: dict[str, Any]) -> list[Endpoint]:
        """Extract all endpoints from the spec."""
        endpoints = []
        paths = spec.get("paths", {})

        for path, path_item in paths.items():
            if not isinstance(path_item, dict):
                continue

            # Get path-level parameters
            path_params = path_item.get("parameters", [])

            for method in self.HTTP_METHODS:
                if method not in path_item:
                    continue

                operation = path_item[method]
                if not isinstance(operation, dict):
                    continue

                endpoint = self._parse_operation(path, method, operation, path_params)
                endpoints.append(endpoint)

        return endpoints

    def _parse_operation(
        self,
        path: str,
        method: str,
        operation: dict[str, Any],
        path_params: list[dict[str, Any]],
    ) -> Endpoint:
        """Parse a single operation into an Endpoint."""
        # Combine path-level and operation-level parameters
        op_params = operation.get("parameters", [])
        all_params = path_params + op_params

        parameters = []
        for param in all_params:
            param = self._resolve_ref(param)
            parameters.append(
                Parameter(
                    name=param.get("name", ""),
                    location=param.get("in", "query"),
                    required=param.get("required", False),
                    description=param.get("description"),
                    param_schema=self._resolve_ref(param.get("schema", {})),
                )
            )

        # Extract request body schema
        request_body_schema = None
        request_body = operation.get("requestBody", {})
        if request_body:
            request_body = self._resolve_ref(request_body)
            content = request_body.get("content", {})
            json_content = content.get("application/json", {})
            if json_content:
                schema = json_content.get("schema", {})
                request_body_schema = self._resolve_ref(schema)

        # Swagger 2.0 uses body parameter instead
        if not request_body_schema:
            for param in all_params:
                param = self._resolve_ref(param)
                if param.get("in") == "body":
                    request_body_schema = self._resolve_ref(param.get("schema", {}))
                    break

        # Extract response schema (200 response)
        response_schema = None
        responses = operation.get("responses", {})
        success_response = responses.get("200") or responses.get("201") or responses.get("default")
        if success_response:
            success_response = self._resolve_ref(success_response)
            content = success_response.get("content", {})
            json_content = content.get("application/json", {})
            if json_content:
                schema = json_content.get("schema", {})
                response_schema = self._resolve_ref(schema)
            # Swagger 2.0
            elif "schema" in success_response:
                response_schema = self._resolve_ref(success_response.get("schema", {}))

        return Endpoint(
            path=path,
            method=method.upper(),
            summary=operation.get("summary"),
            description=operation.get("description"),
            operation_id=operation.get("operationId"),
            tags=operation.get("tags", []),
            parameters=parameters,
            request_body_schema=request_body_schema,
            response_schema=response_schema,
            security=operation.get("security", []),
        )

    def _resolve_ref(self, obj: Any) -> Any:
        """
        Resolve $ref references in the spec.

        Handles references like "#/components/schemas/Pet" or "#/definitions/Pet".
        """
        if not isinstance(obj, dict):
            return obj

        if "$ref" not in obj:
            # Recursively resolve refs in nested objects
            resolved = {}
            for key, value in obj.items():
                if isinstance(value, dict):
                    resolved[key] = self._resolve_ref(value)
                elif isinstance(value, list):
                    resolved[key] = [self._resolve_ref(item) for item in value]
                else:
                    resolved[key] = value
            return resolved

        ref = obj["$ref"]
        if not ref.startswith("#/"):
            return obj

        # Parse the reference path
        parts = ref[2:].split("/")

        # Navigate to the referenced object
        current = self._spec
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return obj  # Could not resolve, return original

        # Recursively resolve refs in the target
        return self._resolve_ref(current)
