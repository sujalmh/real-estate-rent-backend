"""Tests for reporting functionality."""

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
    """Get admin token."""
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
async def test_user_can_create_report(client: AsyncClient):
    """Test that authenticated user can report a listing."""
    # Create listing owner and reporter
    _, owner_token = await create_user_and_token(client)
    _, reporter_token = await create_user_and_token(client)
    
    # Owner creates listing
    listing_id = await create_listing(client, owner_token)
    
    # Reporter reports the listing
    reporter_headers = {"Authorization": f"Bearer {reporter_token}"}
    report_data = {
        "listing_id": listing_id,
        "category": "spam",
        "details": "This listing appears to be spam and doesn't look legitimate"
    }
    
    response = await client.post("/api/v1/reports", json=report_data, headers=reporter_headers)
    assert response.status_code == 201
    
    report = response.json()
    assert report["listing_id"] == listing_id
    assert report["category"] == "spam"
    assert report["status"] == "pending"


@pytest.mark.asyncio
async def test_cannot_duplicate_report(client: AsyncClient):
    """Test that user cannot report same listing twice."""
    # Create users
    _, owner_token = await create_user_and_token(client)
    _, reporter_token = await create_user_and_token(client)
    
    listing_id = await create_listing(client, owner_token)
    
    # First report
    reporter_headers = {"Authorization": f"Bearer {reporter_token}"}
    report_data = {
        "listing_id": listing_id,
        "category": "fraud",
        "details": "This is a fraudulent listing"
    }
    
    response = await client.post("/api/v1/reports", json=report_data, headers=reporter_headers)
    assert response.status_code == 201
    
    # Try to report again
    response = await client.post("/api/v1/reports", json=report_data, headers=reporter_headers)
    assert response.status_code == 400
    assert "already reported" in response.json()["detail"]


@pytest.mark.asyncio
async def test_invalid_category_rejected(client: AsyncClient):
    """Test that invalid report categories are rejected."""
    _, token = await create_user_and_token(client)
    listing_id = await create_listing(client, token)
    
    headers = {"Authorization": f"Bearer {token}"}
    report_data = {
        "listing_id": listing_id,
        "category": "invalid_category",
        "details": "Some details"
    }
    
    response = await client.post("/api/v1/reports", json=report_data, headers=headers)
    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_admin_can_list_reports(client: AsyncClient, admin_user):
    """Test that admin can list all reports."""
    # Create some reports
    _, user1_token = await create_user_and_token(client)
    _, user2_token = await create_user_and_token(client)
    
    listing_id = await create_listing(client, user1_token)
    
    user2_headers = {"Authorization": f"Bearer {user2_token}"}
    report_data = {
        "listing_id": listing_id,
        "category": "inappropriate",
        "details": "This listing contains inappropriate images"
    }
    
    await client.post("/api/v1/reports", json=report_data, headers=user2_headers)
    
    # Admin lists reports
    admin_token = await get_admin_token(client)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    
    response = await client.get("/api/v1/admin/reports", headers=admin_headers)
    assert response.status_code == 200
    
    reports = response.json()
    assert len(reports) >= 1
    
    # Check report includes context
    report = reports[0]
    assert "listing_title" in report
    assert "reporter_name" in report


@pytest.mark.asyncio
async def test_non_admin_cannot_list_reports(client: AsyncClient):
    """Test that regular users cannot list reports."""
    _, user_token = await create_user_and_token(client)
    user_headers = {"Authorization": f"Bearer {user_token}"}
    
    response = await client.get("/api/v1/admin/reports", headers=user_headers)
    assert response.status_code == 403
    assert "Admin access required" in response.json()["detail"]


@pytest.mark.asyncio
async def test_filter_reports_by_status(client: AsyncClient, admin_user):
    """Test filtering reports by status."""
    # Create report
    _, user1_token = await create_user_and_token(client)
    _, user2_token = await create_user_and_token(client)
    
    listing_id = await create_listing(client, user1_token)
    
    user2_headers = {"Authorization": f"Bearer {user2_token}"}
    report_data = {
        "listing_id": listing_id,
        "category": "spam",
        "details": "This is spam"
    }
    
    await client.post("/api/v1/reports", json=report_data, headers=user2_headers)
    
    # Admin filters by pending status
    admin_token = await get_admin_token(client)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    
    response = await client.get("/api/v1/admin/reports?status=pending", headers=admin_headers)
    assert response.status_code == 200
    
    reports = response.json()
    assert len(reports) >= 1
    # All should be pending
    for report in reports:
        assert report["status"] == "pending"


@pytest.mark.asyncio
async def test_report_nonexistent_listing(client: AsyncClient):
    """Test that reporting nonexistent listing returns 404."""
    _, user_token = await create_user_and_token(client)
    user_headers = {"Authorization": f"Bearer {user_token}"}
    
    fake_listing_id = str(uuid.uuid4())
    report_data = {
        "listing_id": fake_listing_id,
        "category": "spam",
        "details": "This is fake"
    }
    
    response = await client.post("/api/v1/reports", json=report_data, headers=user_headers)
    assert response.status_code == 404
    assert "Listing not found" in response.json()["detail"]
