# OpenAPI MCP Server — Claude Code Build Prompts

Use these prompts **sequentially** in Claude Code. Each prompt builds on the previous step. Wait for each step to complete and test before moving to the next.

---

## Prompt 0: Mock Petstore REST API (Test Server)

```
Create a simple mock Petstore REST API using FastAPI that we'll use to test our MCP server locally. 

Create this in a folder called "mock-petstore/" at the project root.

mock-petstore/
├── app.py                 # FastAPI application
├── openapi_spec.json      # Auto-generated OpenAPI spec (we'll export it)
├── requirements.txt       # fastapi, uvicorn
└── README.md

## app.py
Build a FastAPI app with in-memory storage (just a Python dict) that implements:

### Pet endpoints
- GET    /pets                  - List all pets (query params: status, limit, offset)
- GET    /pets/{pet_id}         - Get pet by ID
- POST   /pets                  - Create a new pet (body: { name, species, status, tags? })
- PUT    /pets/{pet_id}         - Update a pet (body: full pet object)
- PATCH  /pets/{pet_id}         - Partial update (body: any subset of fields)
- DELETE /pets/{pet_id}         - Delete a pet

### Store endpoints
- GET    /store/inventory       - Get inventory count grouped by status
- POST   /store/orders          - Place an order (body: { pet_id, quantity })
- GET    /store/orders/{order_id} - Get order by ID

### User endpoints
- GET    /users                 - List all users
- POST   /users                 - Create user (body: { username, email })
- GET    /users/{username}      - Get user by username

## Data models (Pydantic):
- Pet: { id: int (auto), name: str, species: str, status: "available"|"pending"|"sold", tags: list[str] = [] }
- Order: { id: int (auto), pet_id: int, quantity: int, status: "placed"|"approved"|"delivered", created_at: datetime }
- User: { username: str, email: str }

## Requirements:
1. Pre-seed with 10 sample pets on startup (mix of dogs, cats, birds with various statuses)
2. Pre-seed with 2 sample users
3. All endpoints should have clear descriptions and summary in FastAPI decorators (this generates good OpenAPI docs)
4. Support proper HTTP status codes: 200, 201, 404, 422
5. GET /pets should support filtering by status AND pagination via limit/offset
6. Add a simple API key auth via header "X-API-Key" with value "test-key-123" (use FastAPI Depends)
7. The app should run on port 8000: uvicorn app:app --port 8000

## Also create a startup script run.sh:
#!/bin/bash
pip install fastapi uvicorn
uvicorn app:app --host 0.0.0.0 --port 8000 --reload

After creating the server, export the OpenAPI spec by adding a script that hits http://localhost:8000/openapi.json and saves it to mock-petstore/openapi_spec.json

This mock server will be our test target for the MCP bridge. It gives us full control over the data and behavior.
```

---

## Prompt 1: Project Setup

```
Create a new Python MCP server project called "openapi-mcp-bridge" with the following structure:

openapi-mcp-bridge/
├── src/
│   ├── __init__.py
│   ├── server.py              # MCP server entry point
│   ├── config.py              # Configuration loader
│   ├── registry.py            # API registry (manages registered OpenAPI specs)
│   ├── parser.py              # OpenAPI spec parser
│   ├── search/
│   │   ├── __init__.py
│   │   ├── base.py            # SearchProvider abstract interface
│   │   ├── fuzzy.py           # Fuzzy search implementation
│   │   └── embedding.py       # Placeholder for embedding search (future)
│   ├── executor.py            # HTTP request executor
│   └── guardrails.py          # Safety checks (destructive ops, confirmation)
├── config/
│   └── apis.json              # API registration config file
├── tests/
│   ├── __init__.py
│   ├── test_parser.py
│   ├── test_search.py
│   ├── test_executor.py
│   └── test_integration.py
├── pyproject.toml
├── README.md
└── .gitignore

Use these dependencies:
- mcp[cli] (official MCP Python SDK)
- httpx (async HTTP client)
- pyyaml (YAML support for OpenAPI specs)
- thefuzz (fuzzy string matching, formerly fuzzywuzzy)
- pydantic (config validation)

Create the pyproject.toml with these dependencies and a basic README.md explaining the project purpose:
"A generic MCP server that takes any OpenAPI/Swagger specification and exposes it as MCP tools, allowing AI assistants to search, explore, and execute any REST API."

Initialize all files with basic boilerplate. Do NOT implement logic yet — just set up the structure, imports, and class stubs.
```

---

## Prompt 2: Configuration & OpenAPI Parser

```
Now implement the configuration loader and OpenAPI spec parser.

## config.py
Create a Pydantic model for the API configuration:
{
  "apis": [
    {
      "name": "petstore",
      "spec_url": "https://petstore3.swagger.io/api/v3/openapi.json",  // URL or local file path
      "base_url": "https://petstore3.swagger.io/api/v3",
      "auth": {
        "type": "bearer",          // bearer, api_key, basic, none
        "token": "$PETSTORE_KEY",  // supports env variable references with $
        "header_name": "Authorization",  // customizable header name
        "api_key_in": "header"     // for api_key type: header or query
      },
      "settings": {
        "default_page_size": 20,
        "max_batch_size": 50,
        "rate_limit_per_second": 5,
        "confirm_destructive": true
      }
    }
  ]
}

- Auth token values starting with "$" should be resolved from environment variables
- All settings should have sensible defaults
- Validate the config on load

## parser.py
Create an OpenAPI parser that:
1. Accepts a spec URL (JSON/YAML) or local file path
2. Parses the OpenAPI 3.x spec (also handle Swagger 2.0 by converting key fields)
3. Extracts and stores a normalized list of endpoints, each containing:
   - path (e.g., "/pet/{petId}")
   - method (GET, POST, PUT, DELETE, PATCH)
   - summary and description
   - operationId
   - tags
   - parameters (name, in, type, required, description, schema)
   - request body schema (if any)
   - response schema (200 response)
   - security requirements
4. Resolves $ref references within the spec (components/schemas)
5. Stores the parsed result in memory for fast access

Use httpx to fetch remote specs. Handle both JSON and YAML formats.

## registry.py
Create an APIRegistry class that:
1. Loads config from apis.json
2. Parses each registered API spec on startup
3. Stores parsed specs in a dict keyed by API name
4. Provides methods: list_apis(), get_api(name), get_endpoints(api_name)

Write tests in test_parser.py that parse the Petstore spec and verify:
- Correct number of endpoints extracted
- Parameters are properly parsed
- $ref references are resolved
- Both path and query parameters are captured

Use this sample Petstore spec for testing — download from:
https://petstore3.swagger.io/api/v3/openapi.json
Save a local copy in tests/fixtures/petstore.json for offline testing.
```

---

## Prompt 3: Search Provider (Fuzzy)

```
Implement the search functionality.

## search/base.py
Create an abstract SearchProvider interface:
- search(query: str, endpoints: list, limit: int = 5) -> list[SearchResult]
- SearchResult should contain: endpoint data + similarity_score (0.0 to 1.0)

## search/fuzzy.py
Implement FuzzySearchProvider using thefuzz library:
1. For each endpoint, create a searchable text by combining:
   - summary
   - description
   - operationId
   - tags
   - path (split by / and convert to words, e.g., "/pet/{petId}" -> "pet petId")
2. Use thefuzz.fuzz.token_set_ratio to compare the query against each endpoint's searchable text
3. Return results sorted by similarity score descending
4. Include a confidence threshold (default 0.4) — results below this are still returned but flagged as low_confidence: true

## search/embedding.py
Create a placeholder EmbeddingSearchProvider that:
- Has the same interface as FuzzySearchProvider
- Raises NotImplementedError with message "Embedding search not yet implemented. Use FuzzySearchProvider."
- Has TODO comments showing where embeddings would be generated and stored

Important: The search should return full endpoint details (params, body schema, etc.) in each result so we don't need a separate "get details" tool call.

Write tests in test_search.py with these test cases:
1. "find all pets" should match "/pet/findByStatus" with high confidence
2. "create a new pet" should match "POST /pet" with high confidence
3. "delete a pet" should match "DELETE /pet/{petId}" with high confidence
4. "store inventory" should match "/store/inventory"
5. "xyzabc123" (nonsense) should return low confidence results
6. Test that results are sorted by score descending
7. Test the limit parameter works correctly
```

---

## Prompt 4: HTTP Executor with Guardrails

```
Implement the HTTP executor and safety guardrails.

## guardrails.py
Create a Guardrails class that:
1. Identifies destructive operations: DELETE, PUT, PATCH (configurable)
2. Has a method check_operation(method, path, confirmed) that returns:
   - If method is destructive and confirmed=False: returns a warning message asking for confirmation
   - If method is destructive and confirmed=True: allows execution
   - If method is safe (GET, HEAD, OPTIONS): always allows
3. Has a configurable destructive_methods list (default: ["DELETE", "PUT", "PATCH"])

## executor.py
Create an AsyncAPIExecutor class that:
1. Takes an API config (base_url, auth settings)
2. Builds the full URL from base_url + path, substituting path parameters
3. Handles authentication:
   - bearer: adds Authorization: Bearer <token> header
   - api_key: adds key to header or query param based on config
   - basic: adds Authorization: Basic <base64> header
   - none: no auth
4. Executes HTTP requests using httpx.AsyncClient
5. Supports all methods: GET, POST, PUT, DELETE, PATCH
6. Handles query parameters, path parameters, request body (JSON), and custom headers
7. Implements response truncation:
   - If response is a list/array, apply limit and offset
   - Return metadata: { data, status_code, total_count (if detectable), truncated: bool }
8. Handles errors gracefully:
   - HTTP errors (4xx, 5xx) return structured error with status_code and message
   - Connection errors return friendly message
   - Auth errors (401, 403) flag auth_error: true
9. Respects rate limiting from config

Create a BatchExecutor that:
1. Takes a list of request configs
2. Executes them in parallel (with configurable concurrency limit from settings.rate_limit_per_second)
3. Returns a summary: { results: [...], summary: { total, succeeded, failed } }
4. Uses asyncio.Semaphore for concurrency control

Write tests in test_executor.py:
- Test URL building with path parameter substitution
- Test auth header construction for each auth type
- Test response truncation (mock a list response of 100 items, verify only 20 returned with truncated=true)
- Test error handling for 401, 404, 500
- Test batch execution with mock responses
```

---

## Prompt 5: MCP Server — Wire Everything Together

```
Now wire everything into the MCP server with 4 tools.

## server.py
Create the MCP server using the official mcp Python SDK (use FastMCP) with these 4 tools:

### Tool 1: list_apis
- Description: "List all registered OpenAPI/Swagger APIs available for querying"
- Input: none
- Output: list of { name, base_url, description, auth_type, endpoint_count }
- Implementation: calls registry.list_apis()

### Tool 2: search_endpoints
- Description: "Search for API endpoints by natural language description. Returns matching endpoints with full details including parameters, request body schema, and response schema."
- Input: { api: string, query: string, limit?: int (default 5) }
- Output: list of SearchResult with full endpoint details and similarity score
- If api name doesn't exist, return helpful error listing available APIs
- Implementation: calls search_provider.search() on the specified API's endpoints

### Tool 3: execute_endpoint
- Description: "Execute an API endpoint. For destructive operations (DELETE, PUT, PATCH), set confirmed=true after user approval."
- Input: {
    api: string,
    path: string,
    method: string,
    params?: dict,      # query and path params
    body?: dict,        # request body for POST/PUT/PATCH
    headers?: dict,     # additional headers
    limit?: int,        # response truncation limit (default 20)
    offset?: int,       # pagination offset (default 0)
    confirmed?: bool    # required true for destructive operations
  }
- Output: { status_code, data, total_count?, truncated, destructive_warning? }
- Implementation:
  1. Check guardrails first
  2. If destructive and not confirmed, return warning (don't execute)
  3. If safe or confirmed, execute via executor
  4. Truncate response if needed

### Tool 4: batch_execute
- Description: "Execute multiple API endpoints in parallel or sequentially. Always requires user confirmation before execution."
- Input: {
    api: string,
    requests: [{ path, method, params?, body?, headers? }],
    parallel?: bool (default true),
    confirmed?: bool (required true)
  }
- Output: { results: [{ status_code, data, error? }], summary: { total, succeeded, failed } }
- Implementation:
  1. Always require confirmed=true (batch operations are inherently risky)
  2. If not confirmed, return summary of what will be executed and ask for confirmation
  3. If confirmed, execute via batch_executor

Register all tools with the MCP server. Load config from config/apis.json on startup.
Add proper error handling and logging throughout.

Create a config/apis.json with both the local mock server and Petstore:
{
  "apis": [
    {
      "name": "local-petstore",
      "spec_url": "http://localhost:8000/openapi.json",
      "base_url": "http://localhost:8000",
      "auth": { "type": "api_key", "token": "test-key-123", "header_name": "X-API-Key", "api_key_in": "header" },
      "settings": { "default_page_size": 20, "max_batch_size": 50, "rate_limit_per_second": 10, "confirm_destructive": true }
    },
    {
      "name": "petstore-swagger",
      "spec_url": "https://petstore3.swagger.io/api/v3/openapi.json",
      "base_url": "https://petstore3.swagger.io/api/v3",
      "auth": { "type": "api_key", "token": "special-key", "header_name": "api_key", "api_key_in": "header" },
      "settings": { "default_page_size": 20, "max_batch_size": 50, "rate_limit_per_second": 5, "confirm_destructive": true }
    }
  ]
}
```

---

## Prompt 6: Integration Tests

```
Create comprehensive integration tests that simulate real AI interactions with the MCP server.

## test_integration.py
Write tests that run against our local mock Petstore server (mock-petstore/).

Add a pytest fixture that:
1. Starts the mock server: subprocess.Popen(["uvicorn", "mock-petstore.app:app", "--port", "8000"])
2. Waits for it to be ready by polling http://localhost:8000/openapi.json (retry up to 10 times with 1s sleep)
3. Loads the MCP server config pointing to local-petstore
4. Kills the mock server process in teardown

Simulate the following scenarios end-to-end against the LOCAL mock server:

### Scenario 1: Simple Query
- Call list_apis → verify local-petstore is listed
- Call search_endpoints(api="local-petstore", query="find all pets") → verify GET /pets is top result
- Call execute_endpoint(api="local-petstore", path="/pets", method="GET", params={"status": "available"}) → verify 200 response with pre-seeded pets

### Scenario 2: Dependency Chain
- Search for "create pet" → find POST /pets
- Execute POST /pets with body {name: "TestDog", species: "dog", status: "available"}
- Extract the returned pet ID
- Search for "find pet by id" → find GET /pets/{pet_id}
- Execute GET /pets/{pet_id} with the ID from step 2
- Verify the returned pet matches what was created

### Scenario 3: Destructive Operation Guardrail
- Search for "delete pet" → find DELETE /pets/{pet_id}
- Call execute_endpoint with method DELETE and confirmed=false → verify destructive_warning is returned
- Call execute_endpoint with method DELETE and confirmed=true → verify execution proceeds
- Call GET /pets/{pet_id} → verify 404 (pet actually deleted)

### Scenario 4: Batch Execution
- Call batch_execute with 3 GET requests for different pre-seeded pet IDs, confirmed=false → verify it asks for confirmation
- Call batch_execute with confirmed=true → verify all 3 execute and summary shows { total: 3, succeeded: 3, failed: 0 }

### Scenario 5: Error Handling
- Call search_endpoints with non-existent api name → verify helpful error listing available APIs
- Call execute_endpoint with invalid path /nonexistent → verify error response
- Call execute_endpoint with non-existent pet_id → verify 404
- Call search_endpoints with nonsense query "xyzabc123" → verify low confidence results are flagged

### Scenario 6: Response Pagination
- Call execute_endpoint GET /pets with limit=3 → verify only 3 items returned and truncated=true
- Call execute_endpoint GET /pets with limit=3, offset=3 → verify next page of results (different pets)
- Verify no overlap between page 1 and page 2

### Scenario 7: Auth Failure
- Temporarily modify auth config to use wrong API key
- Call execute_endpoint → verify auth_error: true in response
- Restore correct auth config
```

---

## Prompt 7: README & Claude Desktop Config

```
Update the README.md with:

1. Project overview and architecture diagram (use ASCII art)
2. Quick start guide:
   - Installation steps
   - How to register an API (edit config/apis.json)
   - How to run the server
3. Configuration reference (all config options explained)
4. Tool reference (all 4 tools with input/output examples)
5. Usage examples showing the AI conversation flow for each scenario
6. How to add the server to Claude Desktop / Claude Code:
   - Claude Desktop: add to claude_desktop_config.json
   - Claude Code: add to .mcp.json

Generate the Claude Desktop config snippet:
{
  "mcpServers": {
    "openapi-bridge": {
      "command": "python",
      "args": ["-m", "src.server"],
      "cwd": "/path/to/openapi-mcp-bridge",
      "env": {
        "PETSTORE_KEY": "special-key"
      }
    }
  }
}

Also generate a .mcp.json for Claude Code usage.
```

---

## Prompt 8 (Optional): Embedding Search Upgrade

```
Replace the fuzzy search with embedding-based semantic search.

## search/embedding.py
Implement EmbeddingSearchProvider:
1. Use sentence-transformers library with model "all-MiniLM-L6-v2" (small, fast, good quality)
2. On API registration, generate embeddings for each endpoint's searchable text (summary + description + tags + path words)
3. Store embeddings in memory (numpy arrays)
4. On search, embed the query and compute cosine similarity against all endpoint embeddings
5. Return results sorted by similarity score

Add sentence-transformers and numpy to dependencies.

Update server.py to accept a --search-provider flag:
- "fuzzy" (default) uses FuzzySearchProvider
- "embedding" uses EmbeddingSearchProvider

Write comparison tests that run the same queries against both providers and print a comparison table showing which one gives better results for:
- "find all pets" 
- "what animals are available" (synonym test)
- "buy a pet" (semantic similarity test)
- "how many pets are in stock" (intent matching test)
- "remove a specific animal" (synonym + intent test)
```

---

## Tips for Using These Prompts

1. **Run each prompt one at a time** — don't paste them all at once
2. **Start the mock server first** (Prompt 0) — run `cd mock-petstore && bash run.sh` and keep it running
3. **Test after each step** — run `pytest` after prompts 2-6
4. **If something breaks**, tell Claude Code: "The last change broke X. Here's the error: [paste error]. Fix it."
5. **After Prompt 6**, verify all 7 integration test scenarios pass against the local mock server
6. **After Prompt 7**, try connecting to Claude Desktop and test manually with the mock server running
7. **Prompt 8 is optional** — only do it after everything else works
8. **To test against a real API later**, just add a new entry in config/apis.json — the whole point of this project!
