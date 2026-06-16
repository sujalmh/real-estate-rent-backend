"""Tests for moderation functionality."""

import pytest
import uuid
from httpx import AsyncClient
from faker import Faker

fake = Faker()


async def create_user_and_token(client: AsyncClient):
    """Helper to create a user and get auth token."""
    uid = str(uuid.uuid4())[:8]
    user_data = {
        "email": f"user_{uid}_{fake.first_name().lower()}@{fake.domain_name()}",
        "phone": f"+1{str(int(uuid.uuid4()))[-10:]}",
        "name": fake.name(),
        "password": f"Strong{uid}!"
    }
    response = await client.post("/api/v1/users/register", json=user_data)
    user_id = response.json()["id"]
    
    login_data = {"email": user_data["email"], "password": user_data["password"]}
    response = await client.post("/api/v1/auth/login", json=login_data)
    token = response.json()["access_token"]
    
    return user_id, token


async def get_admin_token(client: AsyncClient):
    """Get admin token (admin user already created by seed script)."""
    login_data = {"email": "admin@realestate.com", "password": "Admin@123"}
    response = await client.post("/api/v1/auth/login", json=login_data)
    return response.json()["access_token"]


async def create_listing(client: AsyncClient, token: str):
    """Helper to create a listing."""
    headers = {"Authorization": f"Bearer {token}"}
    listing_data = {
        "type": "rental",
        "title": f"Test Property {fake.street_name()}",
        "description": "A nice property for rent",
        "price_amount": 1500.00,
        "city": fake.city(),
        "country": "India"
    }
    
    response = await client.post("/api/v1/listings", json=listing_data, headers=headers)
    return response.json()["id"]


@pytest.mark.asyncio
async def test_admin_can_view_moderation_queue(client: AsyncClient, admin_user):
    """Test that admin can view moderation queue."""
    # Create regular user and listing
    _, user_token = await create_user_and_token(client)
    listing_id = await create_listing(client, user_token)
    
    # Get admin token
    admin_token = await get_admin_token(client)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    
    # Admin views moderation queue
    response = await client.get("/api/v1/admin/moderation/queue", headers=admin_headers)
    assert response.status_code == 200
    queue = response.json()
    
    # Should see at least the listing we just created
    assert len(queue) >= 1
    listing_ids = [item["id"] for item in queue]
    assert listing_id in listing_ids


@pytest.mark.asyncio
async def test_non_admin_cannot_access_moderation_queue(client: AsyncClient):
    """Test that non-admin users get 403 on moderation endpoints."""
    # Create regular user
    _, user_token = await create_user_and_token(client)
    user_headers = {"Authorization": f"Bearer {user_token}"}
    
    # Try to view moderation queue
    response = await client.get("/api/v1/admin/moderation/queue", headers=user_headers)
    assert response.status_code == 403
    assert "Admin access required" in response.json()["detail"]


@pytest.mark.asyncio
async def test_admin_can_approve_listing(client: AsyncClient, admin_user):
    """Test that admin can approve a listing."""
    # Create listing
    _, user_token = await create_user_and_token(client)
    listing_id = await create_listing(client, user_token)
    
    # Admin approves listing
    admin_token = await get_admin_token(client)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    
    response = await client.post(
        f"/api/v1/admin/listings/{listing_id}/approve",
        headers=admin_headers
    )
    assert response.status_code == 200
    
    listing = response.json()
    assert listing["moderation_status"] == "approved"
    assert listing["status"] == "active"
    assert listing["rejection_reason"] is None


@pytest.mark.asyncio
async def test_admin_can_reject_listing(client: AsyncClient, admin_user):
    """Test that admin can reject a listing with reason."""
    # Create listing
    _, user_token = await create_user_and_token(client)
    listing_id = await create_listing(client, user_token)
    
    # Admin rejects listing
    admin_token = await get_admin_token(client)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    
    rejection_reason = "This listing contains inappropriate content"
    response = await client.post(
        f"/api/v1/admin/listings/{listing_id}/reject",
        json={"reason": rejection_reason},
        headers=admin_headers
    )
    assert response.status_code == 200
    
    listing = response.json()
    assert listing["moderation_status"] == "rejected"
    assert listing["status"] == "deleted"
    assert listing["rejection_reason"] == rejection_reason


@pytest.mark.asyncio
async def test_non_admin_cannot_approve_listing(client: AsyncClient):
    """Test that non-admin users cannot approve listings."""
    # Create two users
    _, user1_token = await create_user_and_token(client)
    _, user2_token = await create_user_and_token(client)
    
    # User 1 creates listing
    listing_id = await create_listing(client, user1_token)
    
    # User 2 tries to approve
    user2_headers = {"Authorization": f"Bearer {user2_token}"}
    response = await client.post(
        f"/api/v1/admin/listings/{listing_id}/approve",
        headers=user2_headers
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_approved_listing_appears_in_search(client: AsyncClient, admin_user):
    """Test that approved listings appear in search results."""
    # Create and approve listing
    _, user_token = await create_user_and_token(client)
    listing_id = await create_listing(client, user_token)
    
    admin_token = await get_admin_token(client)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    
    await client.post(
        f"/api/v1/admin/listings/{listing_id}/approve",
        headers=admin_headers
    )
    
    # Search for listing
    response = await client.post("/api/v1/search/listings", json={})
    assert response.status_code == 200
    
    results = response.json()["items"]
    listing_ids = [item["id"] for item in results]
    assert listing_id in listing_ids


@pytest.mark.asyncio
async def test_rejected_listing_not_in_search(client: AsyncClient, admin_user):
    """Test that rejected listings don't appear in search results."""
    # Create and reject listing
    _, user_token = await create_user_and_token(client)
    listing_id = await create_listing(client, user_token)
    
    admin_token = await get_admin_token(client)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    
    await client.post(
        f"/api/v1/admin/listings/{listing_id}/reject",
        json={"reason": "Test rejection"},
        headers=admin_headers
    )
    
    # Search for listing
    response = await client.post("/api/v1/search/listings", json={})
    assert response.status_code == 200
    
    results = response.json()["items"]
    listing_ids = [item["id"] for item in results]
    assert listing_id not in listing_ids
