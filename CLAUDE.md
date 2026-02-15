# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

OpenAPI MCP Bridge is an MCP server that takes OpenAPI/Swagger specifications and exposes them as MCP tools. It allows AI assistants to search, explore, and execute any REST API.

## Commands

### Install dependencies
```bash
uv sync --all-extras
```

### Run the MCP server
```bash
python -m src.server                           # Fuzzy search (default)
python -m src.server --search-provider embedding  # Embedding search
```

### Run tests
```bash
pytest tests/ -v                               # All tests
pytest tests/test_parser.py -v                 # Single test file
pytest tests/test_parser.py::TestConfig -v     # Single test class
pytest tests/test_integration.py -v            # Integration tests (starts mock server)
```

### Run mock Petstore server (for manual testing)
```bash
uvicorn mock-petstore.app:app --port 8000
```

### Type checking
```bash
pyright src/
```

## Architecture

The system follows a pipeline architecture:

1. **Config** (`config.py`) → Loads `config/apis.json`, resolves `$ENV_VAR` references in auth tokens
2. **Parser** (`parser.py`) → Fetches and parses OpenAPI 3.x/Swagger 2.0 specs, resolves `$ref` references
3. **Registry** (`registry.py`) → Manages multiple APIs, stores parsed specs in memory
4. **Search** (`search/`) → Two providers:
   - `FuzzySearchProvider`: Uses `thefuzz` for string matching
   - `EmbeddingSearchProvider`: Uses `sentence-transformers` for semantic search
5. **Executor** (`executor.py`) → Executes HTTP requests via `httpx`, handles auth, pagination, response truncation
6. **Guardrails** (`guardrails.py`) → Blocks destructive operations (DELETE/PUT/PATCH) unless `confirmed=true`
7. **Server** (`server.py`) → FastMCP server exposing 4 tools: `list_apis`, `search_endpoints`, `execute_endpoint`, `batch_execute`

## Key Design Decisions

- **Async throughout**: Parser, registry, and executor are all async for non-blocking I/O
- **Lazy model loading**: Embedding model only loads when first search is performed
- **Guardrails by default**: Destructive operations require explicit confirmation
- **Environment variable resolution**: Auth tokens can reference env vars with `$VAR_NAME` syntax
- **Pydantic models**: All data structures use Pydantic for validation

## Testing

Integration tests (`test_integration.py`) automatically start/stop the mock Petstore server via pytest fixture. The mock server pre-seeds 10 pets and 2 users for consistent test data.

Test fixtures are in `tests/fixtures/petstore.json` (downloaded from Swagger Petstore).

## Configuration

APIs are registered in `config/apis.json`. Each API requires:
- `name`: Unique identifier
- `spec_url`: URL or local path to OpenAPI spec
- `base_url`: Base URL for requests
- `auth`: Optional auth config (bearer/api_key/basic/none)
