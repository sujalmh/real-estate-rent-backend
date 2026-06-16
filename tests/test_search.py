"""Tests for search and discovery."""

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
        "password": f"Strong{uid}!",
        "name": fake.name()
    }
    await client.post("/api/v1/users/register", json=user_data)
    login_data = {"email": user_data["email"], "password": user_data["password"]}
    response = await client.post("/api/v1/auth/login", json=login_data)
    return response.json()["access_token"]

@pytest.mark.asyncio
async def test_search_listings(client: AsyncClient, db_session):
    """Test searching listings with filters."""
    token = await create_user_and_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    
    # Create 3 listings: 2 active (approved), 1 pending
    # We need to manually approve them in DB to make them searchable
    
    # Listing 1: Rental in Mumbai, 15000 (Active)
    l1 = await client.post("/api/v1/listings", json={
        "type": "rental", "title": "Mumbai Flat", "price_amount": 15000, "city": "Mumbai"
    }, headers=headers)
    id1 = l1.json()["id"]
    
    # Listing 2: PG in Bangalore, 8000 (Active)
    l2 = await client.post("/api/v1/listings", json={
        "type": "pg", "title": "Bangalore PG", "price_amount": 8000, "city": "Bangalore"
    }, headers=headers)
    id2 = l2.json()["id"]
    
    # Listing 3: Rental in Mumbai, 20000 (Pending)
    l3 = await client.post("/api/v1/listings", json={
        "type": "rental", "title": "Mumbai Lux", "price_amount": 20000, "city": "Mumbai"
    }, headers=headers)
    id3 = l3.json()["id"]
    
    # Manually update status in DB for id1 and id2 to active/approved
    from sqlalchemy import text
    await db_session.execute(text(f"UPDATE listings SET status='active', moderation_status='approved' WHERE id IN ('{id1}', '{id2}')"))
    await db_session.commit()
    
    # Test 1: Search All
    response = await client.post("/api/v1/search/listings", json={})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    
    # Test 2: Filter by City
    response = await client.post("/api/v1/search/listings", json={"filters": {"city": "Mumbai"}})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["id"] == id1
    
    # Test 3: Filter by Price Range
    response = await client.post("/api/v1/search/listings", json={"filters": {"price_max": 10000}})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["id"] == id2
    
    # Test 4: Sort by Price Asc
    response = await client.post("/api/v1/search/listings", json={"sort": "price_asc"})
    assert response.status_code == 200
    items = response.json()["items"]
    assert items[0]["id"] == id2 # 8000
    assert items[1]["id"] == id1 # 15000

@pytest.mark.asyncio
async def test_bookmarks(client: AsyncClient):
    """Test bookmarking listings."""
    token = await create_user_and_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    
    # Create listing
    l1 = await client.post("/api/v1/listings", json={
        "type": "rental", "title": "Bookmark Me", "price_amount": 1000
    }, headers=headers)
    listing_id = l1.json()["id"]
    
    # Add bookmark
    response = await client.post("/api/v1/bookmarks", json={"listing_id": listing_id}, headers=headers)
    assert response.status_code == 201
    assert response.json()["listing_id"] == listing_id
    
    # List bookmarks
    response = await client.get("/api/v1/bookmarks", headers=headers)
    assert response.status_code == 200
    assert len(response.json()["items"]) == 1
    assert response.json()["items"][0]["listing"]["id"] == listing_id
    
    # Remove bookmark
    response = await client.delete(f"/api/v1/bookmarks/{listing_id}", headers=headers)
    assert response.status_code == 204
    
    # List empty
    response = await client.get("/api/v1/bookmarks", headers=headers)
    assert response.json()["total"] == 0

@pytest.mark.asyncio
async def test_view_history(client: AsyncClient):
    """Test view history tracking."""
    # User 1 (Owner)
    token1 = await create_user_and_token(client)
    headers1 = {"Authorization": f"Bearer {token1}"}
    
    # User 2 (Viewer)
    token2 = await create_user_and_token(client)
    headers2 = {"Authorization": f"Bearer {token2}"}
    
    # Create listing by User 1
    l1 = await client.post("/api/v1/listings", json={
        "type": "rental", "title": "View Me", "price_amount": 1000
    }, headers=headers1)
    listing_id = l1.json()["id"]
    
    # User 2 views listing
    await client.post(f"/api/v1/listings/{listing_id}/view", headers=headers2)
    
    # Check User 2 history
    response = await client.get("/api/v1/listings/view-history/recent", headers=headers2)
    assert response.status_code == 200
    assert len(response.json()["items"]) == 1
    assert response.json()["items"][0]["id"] == listing_id
    
    # Check listing view count
    response = await client.get(f"/api/v1/listings/{listing_id}", headers=headers1)
    assert response.json()["view_count"] == 1



@pytest.mark.asyncio
async def test_search_default_sort(client: AsyncClient, db_session):
    """Test default sort behavior (Score vs Date)."""
    token = await create_user_and_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    
    # Create Listings
    # L1: Recent but far (Mumbai)
    # L2: Older but close (Pune) - Assuming user is in Pune
    
    l1 = await client.post("/api/v1/listings", json={
        "type": "rental", "title": "Mumbai Recent", "price_amount": 20000, 
        "city": "Mumbai", "latitude": 19.0760, "longitude": 72.8777
    }, headers=headers)
    id1 = l1.json()["id"]
    
    l2 = await client.post("/api/v1/listings", json={
        "type": "rental", "title": "Pune Older", "price_amount": 15000, 
        "city": "Pune", "latitude": 18.5204, "longitude": 73.8567
    }, headers=headers)
    id2 = l2.json()["id"]
    
    from sqlalchemy import text
    import datetime
    
    # Make L2 older by 10 days
    old_date = datetime.datetime.now() - datetime.timedelta(days=10)
    old_date_str = old_date.strftime("%Y-%m-%d %H:%M:%S")
    
    # Approve both, set L2 date older, and POPULATE location (since test DB lacks the migration trigger)
    await db_session.execute(text(f"UPDATE listings SET status='active', moderation_status='approved' WHERE id = '{id1}'"))
    await db_session.execute(text(f"UPDATE listings SET status='active', moderation_status='approved', created_at = '{old_date_str}' WHERE id = '{id2}'"))
    
    # Populate geography column
    await db_session.execute(text(f"UPDATE listings SET location = ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography WHERE id IN ('{id1}', '{id2}')"))
    
    await db_session.commit()
    
    # 1. Default Sort WITHOUT Location -> Should be Date Desc (Newest First) -> L1 then L2
    response = await client.post("/api/v1/search/listings", json={})
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) >= 2
    assert items[0]["id"] == id1
    assert items[1]["id"] == id2
    
    # 2. Default Sort WITH Location (User in Pune) -> Should be Score (Best Match) 
    # Distance: L2 is 0km, L1 is ~150km. L2 (~0 dist) >> L1 (~150km).
    # Even if L1 is fresher, distance weight (0.5) usually dominates freshness (0.2) when distance > 50km.
    # L1 distance score ~0. L2 distance score ~1.
    
    response = await client.post("/api/v1/search/listings", json={
        "user_latitude": 18.5204, 
        "user_longitude": 73.8567
    })
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) >= 2
    assert items[0]["id"] == id2 # Closer one first
    assert items[1]["id"] == id1 # Farther one second
