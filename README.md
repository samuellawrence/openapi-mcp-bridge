# OpenAPI MCP Bridge

A generic MCP server that takes any OpenAPI/Swagger specification and exposes it as MCP tools, allowing AI assistants to search, explore, and execute any REST API.

## Architecture

```
                                    +------------------+
                                    |   Claude / AI    |
                                    +--------+---------+
                                             |
                                             | MCP Protocol
                                             v
+------------------------------------------------------------------+
|                      OpenAPI MCP Bridge                          |
|                                                                  |
|  +-------------+    +-------------+    +------------------+      |
|  |   Config    |    |   Parser    |    |    Registry      |      |
|  | (apis.json) |--->| (OpenAPI)   |--->| (API endpoints)  |      |
|  +-------------+    +-------------+    +------------------+      |
|                                                 |                |
|  +-------------+    +-------------+    +--------v---------+      |
|  | Guardrails  |    |   Search    |    |    Executor      |      |
|  | (safety)    |    |  (fuzzy)    |    |    (httpx)       |      |
|  +-------------+    +-------------+    +------------------+      |
|                                                 |                |
+------------------------------------------------------------------+
                                                  |
                                                  v
                                    +------------------+
                                    |    REST APIs     |
                                    | (Petstore, etc)  |
                                    +------------------+
```

## Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/your-username/openapi-mcp-bridge.git
cd openapi-mcp-bridge

# Install with uv
uv sync --all-extras

# Or with pip
pip install -e ".[dev]"
```

### Register an API

Edit `config/apis.json` to add your API:

```json
{
  "apis": [
    {
      "name": "my-api",
      "spec_url": "https://api.example.com/openapi.json",
      "base_url": "https://api.example.com",
      "auth": {
        "type": "bearer",
        "token": "$MY_API_TOKEN",
        "header_name": "Authorization"
      },
      "settings": {
        "default_page_size": 20,
        "confirm_destructive": true
      }
    }
  ]
}
```

### Run the Server

```bash
# Run with fuzzy search (default)
python -m src.server

# Run with embedding search (better semantic understanding)
python -m src.server --search-provider embedding

# Or set via environment variable
SEARCH_PROVIDER=embedding python -m src.server
```

### Install Embedding Search (Optional)

For better semantic search using sentence-transformers:

```bash
# With uv
uv pip install "sentence-transformers>=2.2.0" "numpy>=1.24.0"

# Or with pip
pip install sentence-transformers numpy
```

## Configuration Reference

### API Configuration

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Unique identifier for the API |
| `spec_url` | string | Yes | URL or local path to OpenAPI spec |
| `base_url` | string | Yes | Base URL for API requests |
| `auth` | object | No | Authentication configuration |
| `settings` | object | No | API-specific settings |

### Authentication Types

| Type | Description | Example |
|------|-------------|---------|
| `bearer` | Bearer token in Authorization header | `Authorization: Bearer <token>` |
| `api_key` | API key in header or query param | `X-API-Key: <token>` |
| `basic` | Basic auth (base64 encoded) | `Authorization: Basic <base64>` |
| `none` | No authentication | - |

Environment variables can be referenced with `$VAR_NAME` syntax.

### Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `default_page_size` | 20 | Default limit for list responses |
| `max_batch_size` | 50 | Maximum requests in batch execution |
| `rate_limit_per_second` | 5 | Rate limiting for requests |
| `confirm_destructive` | true | Require confirmation for DELETE/PUT/PATCH |

## Search Providers

### Fuzzy Search (Default)

Uses `thefuzz` library for string matching. Fast and works without additional dependencies.

```bash
python -m src.server --search-provider fuzzy
```

**Best for:** Exact keyword matching, operation IDs, path names.

### Embedding Search

Uses `sentence-transformers` for semantic similarity. Better understanding of synonyms and intent.

```bash
python -m src.server --search-provider embedding
```

**Best for:** Natural language queries, synonym matching, semantic similarity.

**Comparison:**

| Query | Fuzzy | Embedding |
|-------|-------|-----------|
| "find all pets" | High confidence | High confidence |
| "what animals are available" | Low confidence | **High confidence** |
| "buy a pet" | Mixed results | **Finds store/order** |
| "remove a specific animal" | Mixed results | **Finds DELETE pet** |

## Tool Reference

### 1. list_apis

List all registered OpenAPI/Swagger APIs.

**Input:** None

**Output:**
```json
[
  {
    "name": "petstore",
    "base_url": "https://petstore.example.com",
    "description": "Pet Store API",
    "auth_type": "api_key",
    "endpoint_count": 15
  }
]
```

### 2. search_endpoints

Search for API endpoints by natural language description.

**Input:**
```json
{
  "api": "petstore",
  "query": "find all available pets",
  "limit": 5
}
```

**Output:**
```json
{
  "api": "petstore",
  "query": "find all available pets",
  "results": [
    {
      "endpoint": {
        "path": "/pet/findByStatus",
        "method": "GET",
        "summary": "Finds Pets by status",
        "parameters": [...]
      },
      "similarity_score": 0.85,
      "low_confidence": false
    }
  ],
  "total_results": 5
}
```

### 3. execute_endpoint

Execute an API endpoint.

**Input:**
```json
{
  "api": "petstore",
  "path": "/pet/{petId}",
  "method": "GET",
  "params": {"petId": 123},
  "limit": 20,
  "offset": 0,
  "confirmed": false
}
```

**Output:**
```json
{
  "status_code": 200,
  "data": {"id": 123, "name": "Buddy", "status": "available"},
  "truncated": false,
  "auth_error": false
}
```

For destructive operations (DELETE, PUT, PATCH), set `confirmed: true`.

### 4. batch_execute

Execute multiple API endpoints in parallel.

**Input:**
```json
{
  "api": "petstore",
  "requests": [
    {"path": "/pet/1", "method": "GET"},
    {"path": "/pet/2", "method": "GET"},
    {"path": "/pet/3", "method": "GET"}
  ],
  "parallel": true,
  "confirmed": true
}
```

**Output:**
```json
{
  "results": [...],
  "summary": {"total": 3, "succeeded": 3, "failed": 0}
}
```

## Usage Examples

### Example 1: Simple Query

```
User: What pets are available in the store?

AI: Let me search for that endpoint and get the data.
    1. search_endpoints(api="petstore", query="find available pets")
    2. execute_endpoint(api="petstore", path="/pet/findByStatus",
                        method="GET", params={"status": "available"})

    Result: Found 6 available pets: Buddy (dog), Whiskers (cat), ...
```

### Example 2: Creating a Resource

```
User: Add a new pet named "Max" to the store.

AI: 1. search_endpoints(api="petstore", query="create new pet")
    2. execute_endpoint(api="petstore", path="/pet", method="POST",
                        body={"name": "Max", "species": "dog", "status": "available"})

    Result: Created pet with ID 15.
```

### Example 3: Destructive Operation

```
User: Delete pet #15.

AI: 1. execute_endpoint(api="petstore", path="/pet/{petId}", method="DELETE",
                        params={"petId": 15}, confirmed=false)

    Warning: This is a destructive operation. Set confirmed=true to proceed.

User: Yes, go ahead.

AI: 2. execute_endpoint(..., confirmed=true)

    Result: Pet #15 deleted successfully.
```

## Claude Desktop Integration

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "openapi-bridge": {
      "command": "python",
      "args": ["-m", "src.server"],
      "cwd": "/path/to/openapi-mcp-bridge",
      "env": {
        "PETSTORE_KEY": "your-api-key"
      }
    }
  }
}
```

## Claude Code Integration

Create `.mcp.json` in your project root:

```json
{
  "mcpServers": {
    "openapi-bridge": {
      "command": "python",
      "args": ["-m", "src.server"],
      "cwd": "/path/to/openapi-mcp-bridge",
      "env": {
        "PETSTORE_KEY": "your-api-key"
      }
    }
  }
}
```

## Testing

### Run Unit Tests

```bash
pytest tests/test_parser.py tests/test_search.py tests/test_executor.py -v
```

### Run Integration Tests

```bash
# Requires mock server to start automatically
pytest tests/test_integration.py -v
```

### Start Mock Server Manually

```bash
cd mock-petstore
./run.sh
```

## Development

### Project Structure

```
openapi-mcp-bridge/
├── src/
│   ├── __init__.py
│   ├── server.py          # MCP server with 4 tools
│   ├── config.py          # Configuration loader
│   ├── parser.py          # OpenAPI spec parser
│   ├── registry.py        # API registry
│   ├── executor.py        # HTTP request executor
│   ├── guardrails.py      # Safety checks
│   └── search/
│       ├── base.py        # Search interface
│       ├── fuzzy.py       # Fuzzy search
│       └── embedding.py   # Embedding search (placeholder)
├── config/
│   └── apis.json          # API registrations
├── mock-petstore/         # Test server
├── tests/
└── pyproject.toml
```

## License

MIT
