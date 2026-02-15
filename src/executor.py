"""HTTP request executor for API calls."""

import asyncio
import base64
import re
from typing import Any

import httpx
from pydantic import BaseModel

from .config import APIConfig


class ExecutionResult(BaseModel):
    """Result of an API execution."""

    status_code: int
    data: Any
    total_count: int | None = None
    truncated: bool = False
    auth_error: bool = False
    error: str | None = None


class BatchResult(BaseModel):
    """Result of a batch execution."""

    results: list[ExecutionResult]
    summary: dict[str, int]  # {"total": N, "succeeded": N, "failed": N}


class AsyncAPIExecutor:
    """Async HTTP executor for API calls."""

    def __init__(self, config: APIConfig):
        """
        Initialize the executor.

        Args:
            config: API configuration including base_url and auth settings.
        """
        self.config = config
        self.base_url = config.base_url.rstrip("/")

    async def execute(
        self,
        path: str,
        method: str,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> ExecutionResult:
        """
        Execute an API request.

        Args:
            path: API path (e.g., "/pets/{petId}").
            method: HTTP method.
            params: Query and path parameters.
            body: Request body for POST/PUT/PATCH.
            headers: Additional headers.
            limit: Response truncation limit.
            offset: Pagination offset.

        Returns:
            ExecutionResult with status_code, data, and metadata.
        """
        params = params or {}
        headers = headers or {}

        # Build URL with path parameter substitution
        url = self._build_url(path, params)

        # Build headers with auth
        request_headers = self._build_headers()
        request_headers.update(headers)

        # Extract query params (non-path params)
        query_params = self._extract_query_params(path, params)

        # Add pagination params if provided
        if limit is not None:
            query_params["limit"] = limit
        if offset is not None:
            query_params["offset"] = offset

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.request(
                    method=method.upper(),
                    url=url,
                    params=query_params if query_params else None,
                    json=body if body else None,
                    headers=request_headers,
                )

                # Parse response
                try:
                    data = response.json()
                except Exception:
                    data = response.text

                # Check for auth errors
                auth_error = response.status_code in (401, 403)

                # Handle list truncation
                truncated = False
                total_count = None
                if isinstance(data, list) and limit is not None:
                    total_count = len(data)
                    if len(data) > limit:
                        data = data[:limit]
                        truncated = True

                # Handle error responses
                error = None
                if response.status_code >= 400:
                    if isinstance(data, dict) and "message" in data:
                        error = data["message"]
                    elif isinstance(data, dict) and "detail" in data:
                        error = data["detail"]
                    elif isinstance(data, str):
                        error = data
                    else:
                        error = f"HTTP {response.status_code}"

                return ExecutionResult(
                    status_code=response.status_code,
                    data=data,
                    total_count=total_count,
                    truncated=truncated,
                    auth_error=auth_error,
                    error=error,
                )

        except httpx.ConnectError as e:
            return ExecutionResult(
                status_code=0,
                data=None,
                error=f"Connection error: Could not connect to {self.base_url}",
            )
        except httpx.TimeoutException:
            return ExecutionResult(
                status_code=0,
                data=None,
                error="Request timed out",
            )
        except Exception as e:
            return ExecutionResult(
                status_code=0,
                data=None,
                error=f"Request failed: {str(e)}",
            )

    def _build_url(self, path: str, params: dict[str, Any]) -> str:
        """
        Build full URL with path parameter substitution.

        Args:
            path: API path with placeholders like {petId}.
            params: Parameters including path params.

        Returns:
            Full URL with substituted path parameters.
        """
        # Find path parameters in the path
        path_param_pattern = r"\{(\w+)\}"
        path_params = re.findall(path_param_pattern, path)

        # Substitute path parameters
        result_path = path
        for param_name in path_params:
            if param_name in params:
                result_path = result_path.replace(
                    f"{{{param_name}}}", str(params[param_name])
                )

        return f"{self.base_url}{result_path}"

    def _extract_query_params(
        self, path: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Extract query parameters (exclude path params).

        Args:
            path: API path with placeholders.
            params: All parameters.

        Returns:
            Dict of query parameters only.
        """
        # Find path parameter names
        path_param_pattern = r"\{(\w+)\}"
        path_params = set(re.findall(path_param_pattern, path))

        # Return non-path params
        return {k: v for k, v in params.items() if k not in path_params}

    def _build_headers(self) -> dict[str, str]:
        """
        Build request headers including authentication.

        Returns:
            Dict of headers.
        """
        headers: dict[str, str] = {}

        auth = self.config.auth
        token = auth.token or ""

        if auth.type == "bearer":
            headers[auth.header_name] = f"Bearer {token}"

        elif auth.type == "api_key":
            if auth.api_key_in == "header":
                headers[auth.header_name] = token
            # query param handled separately in execute()

        elif auth.type == "basic":
            # Token should be "username:password"
            encoded = base64.b64encode(token.encode()).decode()
            headers[auth.header_name] = f"Basic {encoded}"

        # Add common headers
        headers["Content-Type"] = "application/json"
        headers["Accept"] = "application/json"

        return headers


class BatchExecutor:
    """Execute multiple API requests in parallel."""

    def __init__(self, executor: AsyncAPIExecutor, concurrency: int = 5):
        """
        Initialize batch executor.

        Args:
            executor: The API executor to use for requests.
            concurrency: Maximum concurrent requests.
        """
        self.executor = executor
        self.concurrency = concurrency

    async def execute_batch(
        self,
        requests: list[dict[str, Any]],
        parallel: bool = True,
    ) -> BatchResult:
        """
        Execute multiple requests.

        Args:
            requests: List of request configs, each with:
                - path: API path
                - method: HTTP method
                - params: Optional parameters
                - body: Optional request body
                - headers: Optional headers
            parallel: If True, execute in parallel with concurrency limit.

        Returns:
            BatchResult with all results and summary.
        """
        if parallel:
            results = await self._execute_parallel(requests)
        else:
            results = await self._execute_sequential(requests)

        # Build summary
        succeeded = sum(1 for r in results if 200 <= r.status_code < 400)
        failed = sum(1 for r in results if r.status_code < 200 or r.status_code >= 400)

        return BatchResult(
            results=results,
            summary={
                "total": len(results),
                "succeeded": succeeded,
                "failed": failed,
            },
        )

    async def _execute_parallel(
        self, requests: list[dict[str, Any]]
    ) -> list[ExecutionResult]:
        """Execute requests in parallel with semaphore."""
        semaphore = asyncio.Semaphore(self.concurrency)

        async def execute_with_semaphore(req: dict[str, Any]) -> ExecutionResult:
            async with semaphore:
                return await self.executor.execute(
                    path=req["path"],
                    method=req["method"],
                    params=req.get("params"),
                    body=req.get("body"),
                    headers=req.get("headers"),
                )

        tasks = [execute_with_semaphore(req) for req in requests]
        return await asyncio.gather(*tasks)

    async def _execute_sequential(
        self, requests: list[dict[str, Any]]
    ) -> list[ExecutionResult]:
        """Execute requests sequentially."""
        results = []
        for req in requests:
            result = await self.executor.execute(
                path=req["path"],
                method=req["method"],
                params=req.get("params"),
                body=req.get("body"),
                headers=req.get("headers"),
            )
            results.append(result)
        return results
