"""Mock Petstore REST API for testing the OpenAPI MCP Bridge."""

from datetime import datetime
from enum import Enum
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, EmailStr, Field

app = FastAPI(
    title="Mock Petstore API",
    description="A mock Petstore API for testing the OpenAPI MCP Bridge",
    version="1.0.0",
)


# --- Auth ---
API_KEY = "test-key-123"


def verify_api_key(x_api_key: str = Header(..., alias="X-API-Key")):
    """Verify the API key header."""
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key


# --- Enums ---
class PetStatus(str, Enum):
    available = "available"
    pending = "pending"
    sold = "sold"


class OrderStatus(str, Enum):
    placed = "placed"
    approved = "approved"
    delivered = "delivered"


# --- Models ---
class PetCreate(BaseModel):
    name: str = Field(..., description="Name of the pet")
    species: str = Field(..., description="Species of the pet (dog, cat, bird, etc.)")
    status: PetStatus = Field(default=PetStatus.available, description="Pet status")
    tags: list[str] = Field(default_factory=list, description="Tags for the pet")


class PetUpdate(BaseModel):
    name: Optional[str] = None
    species: Optional[str] = None
    status: Optional[PetStatus] = None
    tags: Optional[list[str]] = None


class Pet(BaseModel):
    id: int
    name: str
    species: str
    status: PetStatus
    tags: list[str] = []


class OrderCreate(BaseModel):
    pet_id: int = Field(..., description="ID of the pet to order")
    quantity: int = Field(default=1, ge=1, description="Quantity to order")


class Order(BaseModel):
    id: int
    pet_id: int
    quantity: int
    status: OrderStatus
    created_at: datetime


class UserCreate(BaseModel):
    username: str = Field(..., description="Username")
    email: str = Field(..., description="User email")


class User(BaseModel):
    username: str
    email: str


# --- In-memory storage ---
pets_db: dict[int, Pet] = {}
orders_db: dict[int, Order] = {}
users_db: dict[str, User] = {}
pet_id_counter = 1
order_id_counter = 1


# --- Seed data ---
def seed_data():
    """Pre-seed the database with sample data."""
    global pet_id_counter, order_id_counter

    sample_pets = [
        {"name": "Buddy", "species": "dog", "status": PetStatus.available, "tags": ["friendly", "trained"]},
        {"name": "Whiskers", "species": "cat", "status": PetStatus.available, "tags": ["indoor"]},
        {"name": "Tweety", "species": "bird", "status": PetStatus.pending, "tags": ["singing"]},
        {"name": "Max", "species": "dog", "status": PetStatus.sold, "tags": ["guard dog"]},
        {"name": "Luna", "species": "cat", "status": PetStatus.available, "tags": ["playful", "kitten"]},
        {"name": "Rocky", "species": "dog", "status": PetStatus.available, "tags": ["energetic"]},
        {"name": "Polly", "species": "bird", "status": PetStatus.available, "tags": ["talking"]},
        {"name": "Shadow", "species": "cat", "status": PetStatus.pending, "tags": ["shy"]},
        {"name": "Charlie", "species": "dog", "status": PetStatus.available, "tags": ["puppy", "cute"]},
        {"name": "Coco", "species": "bird", "status": PetStatus.sold, "tags": ["colorful"]},
    ]

    for pet_data in sample_pets:
        pets_db[pet_id_counter] = Pet(id=pet_id_counter, **pet_data)
        pet_id_counter += 1

    sample_users = [
        {"username": "john_doe", "email": "john@example.com"},
        {"username": "jane_smith", "email": "jane@example.com"},
    ]

    for user_data in sample_users:
        users_db[user_data["username"]] = User(**user_data)


@app.on_event("startup")
async def startup_event():
    """Seed the database on startup."""
    seed_data()


# --- Pet Endpoints ---
@app.get("/pets", response_model=list[Pet], summary="List all pets", tags=["pets"])
async def list_pets(
    status: Optional[PetStatus] = Query(None, description="Filter by pet status"),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of pets to return"),
    offset: int = Query(0, ge=0, description="Number of pets to skip"),
    _: str = Depends(verify_api_key),
):
    """List all pets with optional filtering by status and pagination."""
    pets = list(pets_db.values())

    if status:
        pets = [p for p in pets if p.status == status]

    return pets[offset : offset + limit]


@app.get("/pets/{pet_id}", response_model=Pet, summary="Get pet by ID", tags=["pets"])
async def get_pet(pet_id: int, _: str = Depends(verify_api_key)):
    """Get a specific pet by its ID."""
    if pet_id not in pets_db:
        raise HTTPException(status_code=404, detail="Pet not found")
    return pets_db[pet_id]


@app.post("/pets", response_model=Pet, status_code=201, summary="Create a new pet", tags=["pets"])
async def create_pet(pet: PetCreate, _: str = Depends(verify_api_key)):
    """Create a new pet in the store."""
    global pet_id_counter
    new_pet = Pet(id=pet_id_counter, **pet.model_dump())
    pets_db[pet_id_counter] = new_pet
    pet_id_counter += 1
    return new_pet


@app.put("/pets/{pet_id}", response_model=Pet, summary="Update a pet", tags=["pets"])
async def update_pet(pet_id: int, pet: PetCreate, _: str = Depends(verify_api_key)):
    """Update an existing pet (full replacement)."""
    if pet_id not in pets_db:
        raise HTTPException(status_code=404, detail="Pet not found")
    updated_pet = Pet(id=pet_id, **pet.model_dump())
    pets_db[pet_id] = updated_pet
    return updated_pet


@app.patch("/pets/{pet_id}", response_model=Pet, summary="Partial update a pet", tags=["pets"])
async def patch_pet(pet_id: int, pet: PetUpdate, _: str = Depends(verify_api_key)):
    """Partially update an existing pet."""
    if pet_id not in pets_db:
        raise HTTPException(status_code=404, detail="Pet not found")

    existing_pet = pets_db[pet_id]
    update_data = pet.model_dump(exclude_unset=True)

    updated_pet = Pet(**{**existing_pet.model_dump(), **update_data})
    pets_db[pet_id] = updated_pet
    return updated_pet


@app.delete("/pets/{pet_id}", status_code=204, summary="Delete a pet", tags=["pets"])
async def delete_pet(pet_id: int, _: str = Depends(verify_api_key)):
    """Delete a pet from the store."""
    if pet_id not in pets_db:
        raise HTTPException(status_code=404, detail="Pet not found")
    del pets_db[pet_id]


# --- Store Endpoints ---
@app.get("/store/inventory", summary="Get store inventory", tags=["store"])
async def get_inventory(_: str = Depends(verify_api_key)):
    """Get inventory count grouped by pet status."""
    inventory = {"available": 0, "pending": 0, "sold": 0}
    for pet in pets_db.values():
        inventory[pet.status.value] += 1
    return inventory


@app.post("/store/orders", response_model=Order, status_code=201, summary="Place an order", tags=["store"])
async def create_order(order: OrderCreate, _: str = Depends(verify_api_key)):
    """Place a new order for a pet."""
    global order_id_counter

    if order.pet_id not in pets_db:
        raise HTTPException(status_code=404, detail="Pet not found")

    new_order = Order(
        id=order_id_counter,
        pet_id=order.pet_id,
        quantity=order.quantity,
        status=OrderStatus.placed,
        created_at=datetime.now(),
    )
    orders_db[order_id_counter] = new_order
    order_id_counter += 1
    return new_order


@app.get("/store/orders/{order_id}", response_model=Order, summary="Get order by ID", tags=["store"])
async def get_order(order_id: int, _: str = Depends(verify_api_key)):
    """Get a specific order by its ID."""
    if order_id not in orders_db:
        raise HTTPException(status_code=404, detail="Order not found")
    return orders_db[order_id]


# --- User Endpoints ---
@app.get("/users", response_model=list[User], summary="List all users", tags=["users"])
async def list_users(_: str = Depends(verify_api_key)):
    """List all registered users."""
    return list(users_db.values())


@app.post("/users", response_model=User, status_code=201, summary="Create a new user", tags=["users"])
async def create_user(user: UserCreate, _: str = Depends(verify_api_key)):
    """Create a new user."""
    if user.username in users_db:
        raise HTTPException(status_code=400, detail="Username already exists")
    new_user = User(**user.model_dump())
    users_db[user.username] = new_user
    return new_user


@app.get("/users/{username}", response_model=User, summary="Get user by username", tags=["users"])
async def get_user(username: str, _: str = Depends(verify_api_key)):
    """Get a specific user by username."""
    if username not in users_db:
        raise HTTPException(status_code=404, detail="User not found")
    return users_db[username]
