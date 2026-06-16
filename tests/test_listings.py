"""Tests for listing management."""

import pytest
import uuid
from httpx import AsyncClient
from faker import Faker

fake = Faker()

async def create_user_and_token(client: AsyncClient):
    """Helper to create a user and get auth token."""
    # Register
    uid = str(uuid.uuid4())[:8]
    user_data = {
        "email": f"user_{uid}_{fake.first_name().lower()}@{fake.domain_name()}",
        "phone": f"+1{str(int(uuid.uuid4()))[-10:]}",
        "name": fake.name(),
        "password": f"Strong{uid}!"
    }
    await client.post("/api/v1/users/register", json=user_data)
    
    # Login
    login_data = {"email": user_data["email"], "password": user_data["password"]}
    response = await client.post("/api/v1/auth/login", json=login_data)
    token = response.json()["access_token"]
    
    return user_data, token

@pytest.mark.asyncio
async def test_create_and_get_listing(client: AsyncClient):
    """Test creating and retrieving a listing."""
    user, token = await create_user_and_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    
    # Create listing
    listing_data = {
        "type": "rental",
        "title": "Test Apartment",
        "description": "A nice place",
        "price_amount": 1500.00,
        "city": "Test City",
        "country": "India"
    }
    
    response = await client.post("/api/v1/listings", json=listing_data, headers=headers)
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == listing_data["title"]
    assert data["status"] == "pending_review"
    listing_id = data["id"]
    
    # Get listing
    # Note: Owner viewing own listing doesn't increment view count
    response = await client.get(f"/api/v1/listings/{listing_id}", headers=headers)
    assert response.status_code == 200
    assert response.json()["id"] == listing_id
    assert response.json()["view_count"] == 0

@pytest.mark.asyncio
async def test_update_listing(client: AsyncClient):
    """Test updating a listing."""
    user, token = await create_user_and_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    
    # Create
    listing_data = {
        "type": "rental", 
        "title": "Original Title",
        "price_amount": 1000,
        "city": "City"
    }
    response = await client.post("/api/v1/listings", json=listing_data, headers=headers)
    listing_id = response.json()["id"]
    
    # Update partial
    update_data = {"title": "New Title"}
    response = await client.put(f"/api/v1/listings/{listing_id}", json=update_data, headers=headers)
    assert response.status_code == 200
    assert response.json()["title"] == "New Title"
    assert float(response.json()["price_amount"]) == 1000.0  # Unchanged

@pytest.mark.asyncio
async def test_listing_status_lifecycle(client: AsyncClient):
    """Test pause, reactivate, delete lifecycle."""
    user, token = await create_user_and_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    
    # Create
    listing_data = {"type": "rental", "title": "Lifecycle Test", "price_amount": 1000}
    response = await client.post("/api/v1/listings", json=listing_data, headers=headers)
    listing_id = response.json()["id"]
    
    # Pause
    response = await client.patch(f"/api/v1/listings/{listing_id}/pause", headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "paused"
    
    # Reactivate
    response = await client.patch(f"/api/v1/listings/{listing_id}/reactivate", headers=headers)
    assert response.status_code == 200
    # Should go back to pending_review because it wasn't approved yet
    assert response.json()["status"] == "pending_review"
    
    # Delete
    response = await client.delete(f"/api/v1/listings/{listing_id}", headers=headers)
    assert response.status_code == 204
    
    # Verify deleted
    response = await client.get(f"/api/v1/listings/{listing_id}", headers=headers)
    assert response.status_code == 200 # Owner can see deleted
    assert response.json()["status"] == "deleted"

@pytest.mark.asyncio
async def test_ownership_permissions(client: AsyncClient):
    """Test that users cannot modify others' listings."""
    # User 1
    _, token1 = await create_user_and_token(client)
    headers1 = {"Authorization": f"Bearer {token1}"}
    
    # User 2
    _, token2 = await create_user_and_token(client)
    headers2 = {"Authorization": f"Bearer {token2}"}
    
    # User 1 creates listing
    listing_data = {"type": "rental", "title": "User1 Listing", "price_amount": 1000}
    response = await client.post("/api/v1/listings", json=listing_data, headers=headers1)
    listing_id = response.json()["id"]
    
    # User 2 tries to update
    response = await client.put(f"/api/v1/listings/{listing_id}", json={"title": "Hacked"}, headers=headers2)
    assert response.status_code == 403
    
    # User 2 tries to delete
    response = await client.delete(f"/api/v1/listings/{listing_id}", headers=headers2)
    assert response.status_code == 403
