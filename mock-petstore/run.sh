#!/bin/bash
# Run the Mock Petstore API server

set -e

cd "$(dirname "$0")"

# Install dependencies if needed
pip install -q fastapi uvicorn

# Start the server
echo "Starting Mock Petstore API on http://localhost:8000"
echo "OpenAPI spec available at http://localhost:8000/openapi.json"
echo "API docs available at http://localhost:8000/docs"
echo ""
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
