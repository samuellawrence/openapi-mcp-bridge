# Mock Petstore API

A simple mock Petstore REST API built with FastAPI for testing the OpenAPI MCP Bridge.

## Quick Start

```bash
# Run the server
./run.sh

# Or manually
uvicorn app:app --port 8000 --reload
```

## Endpoints

### Pets
- `GET /pets` - List all pets (query params: status, limit, offset)
- `GET /pets/{pet_id}` - Get pet by ID
- `POST /pets` - Create a new pet
- `PUT /pets/{pet_id}` - Update a pet (full replacement)
- `PATCH /pets/{pet_id}` - Partial update a pet
- `DELETE /pets/{pet_id}` - Delete a pet

### Store
- `GET /store/inventory` - Get inventory count by status
- `POST /store/orders` - Place an order
- `GET /store/orders/{order_id}` - Get order by ID

### Users
- `GET /users` - List all users
- `POST /users` - Create a new user
- `GET /users/{username}` - Get user by username

## Authentication

All endpoints require an API key header:

```
X-API-Key: test-key-123
```

## Pre-seeded Data

The server starts with:
- 10 sample pets (mix of dogs, cats, birds with various statuses)
- 2 sample users (john_doe, jane_smith)

## API Documentation

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- OpenAPI JSON: http://localhost:8000/openapi.json
