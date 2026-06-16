"""Tests for lead management functionality."""

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
    response = await client.post("/api/v1/users/register", json=user_data)
    user_id = response.json()["id"]
    
    # Login
    login_data = {"email": user_data["email"], "password": user_data["password"]}
    response = await client.post("/api/v1/auth/login", json=login_data)
    token = response.json()["access_token"]
    
    return user_id, token


async def create_listing(client: AsyncClient, token: str):
    """Helper to create an active listing."""
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
async def test_automatic_lead_creation(client: AsyncClient):
    """Test that a lead is automatically created when a conversation starts."""
    # Create owner and seeker
    owner_id, owner_token = await create_user_and_token(client)
    seeker_id, seeker_token = await create_user_and_token(client)
    
    # Owner creates a listing
    listing_id = await create_listing(client, owner_token)
    
    # Seeker creates a conversation (which should create a lead)
    seeker_headers = {"Authorization": f"Bearer {seeker_token}"}
    conv_data = {
        "listing_id": listing_id,
        "recipient_id": owner_id
    }
    
    response = await client.post("/api/v1/conversations", json=conv_data, headers=seeker_headers)
    assert response.status_code == 201
    conversation_id = response.json()["id"]
    
    # Owner checks their leads
    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    response = await client.get("/api/v1/leads", headers=owner_headers)
    assert response.status_code == 200
    leads = response.json()
    
    # Should have at least one lead
    assert len(leads) >= 1
    
    # Find the lead for this conversation
    lead = next((l for l in leads if l["conversation_id"] == conversation_id), None)
    assert lead is not None
    assert lead["listing_id"] == listing_id
    assert lead["seeker_id"] == seeker_id
    assert lead["owner_id"] == owner_id
    assert lead["status"] == "new"
    
    # Seeker also sees the lead
    response = await client.get("/api/v1/leads", headers=seeker_headers)
    assert response.status_code == 200
    seeker_leads = response.json()
    assert len(seeker_leads) >= 1
    
    seeker_lead = next((l for l in seeker_leads if l["conversation_id"] == conversation_id), None)
    assert seeker_lead is not None


@pytest.mark.asyncio
async def test_update_lead_status(client: AsyncClient):
    """Test updating lead status."""
    # Create owner and seeker
    owner_id, owner_token = await create_user_and_token(client)
    seeker_id, seeker_token = await create_user_and_token(client)
    
    # Create listing and conversation
    listing_id = await create_listing(client, owner_token)
    
    seeker_headers = {"Authorization": f"Bearer {seeker_token}"}
    conv_data = {"listing_id": listing_id, "recipient_id": owner_id}
    
    response = await client.post("/api/v1/conversations", json=conv_data, headers=seeker_headers)
    conversation_id = response.json()["id"]
    
    # Get the lead ID
    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    response = await client.get("/api/v1/leads", headers=owner_headers)
    leads = response.json()
    lead = next(l for l in leads if l["conversation_id"] == conversation_id)
    lead_id = lead["id"]
    
    # Owner updates lead status to "contacted"
    update_data = {"status": "contacted"}
    response = await client.patch(
        f"/api/v1/leads/{lead_id}/status",
        json=update_data,
        headers=owner_headers
    )
    assert response.status_code == 200
    updated_lead = response.json()
    assert updated_lead["status"] == "contacted"
    
    # Update to "qualified"
    update_data = {"status": "qualified"}
    response = await client.patch(
        f"/api/v1/leads/{lead_id}/status",
        json=update_data,
        headers=owner_headers
    )
    assert response.status_code == 200
    assert response.json()["status"] == "qualified"
    
    # Update to "converted"
    update_data = {"status": "converted"}
    response = await client.patch(
        f"/api/v1/leads/{lead_id}/status",
        json=update_data,
        headers=owner_headers
    )
    assert response.status_code == 200
    assert response.json()["status"] == "converted"


@pytest.mark.asyncio
async def test_filter_leads_by_status(client: AsyncClient):
    """Test filtering leads by status."""
    # Create owner and seekers
    owner_id, owner_token = await create_user_and_token(client)
    seeker1_id, seeker1_token = await create_user_and_token(client)
    seeker2_id, seeker2_token = await create_user_and_token(client)
    
    # Create listing
    listing_id = await create_listing(client, owner_token)
    
    # Seeker 1 creates conversation
    seeker1_headers = {"Authorization": f"Bearer {seeker1_token}"}
    conv_data = {"listing_id": listing_id, "recipient_id": owner_id}
    response = await client.post("/api/v1/conversations", json=conv_data, headers=seeker1_headers)
    conv1_id = response.json()["id"]
    
    # Seeker 2 creates conversation
    seeker2_headers = {"Authorization": f"Bearer {seeker2_token}"}
    conv_data = {"listing_id": listing_id, "recipient_id": owner_id}
    response = await client.post("/api/v1/conversations", json=conv_data, headers=seeker2_headers)
    conv2_id = response.json()["id"]
    
    # Get leads and update statuses
    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    response = await client.get("/api/v1/leads", headers=owner_headers)
    leads = response.json()
    
    lead1 = next(l for l in leads if l["conversation_id"] == conv1_id)
    lead2 = next(l for l in leads if l["conversation_id"] == conv2_id)
    
    # Update lead1 to "contacted"
    await client.patch(
        f"/api/v1/leads/{lead1['id']}/status",
        json={"status": "contacted"},
        headers=owner_headers
    )
    
    # Leave lead2 as "new"
    
    # Filter by "new" status
    response = await client.get("/api/v1/leads?status=new", headers=owner_headers)
    assert response.status_code == 200
    new_leads = response.json()
    assert len([l for l in new_leads if l["status"] == "new"]) >= 1
    assert any(l["id"] == lead2["id"] for l in new_leads)
    
    # Filter by "contacted" status
    response = await client.get("/api/v1/leads?status=contacted", headers=owner_headers)
    assert response.status_code == 200
    contacted_leads = response.json()
    assert len([l for l in contacted_leads if l["status"] == "contacted"]) >= 1
    assert any(l["id"] == lead1["id"] for l in contacted_leads)


@pytest.mark.asyncio
async def test_lead_permissions(client: AsyncClient):
    """Test that only participants can update lead status."""
    # Create owner, seeker, and stranger
    owner_id, owner_token = await create_user_and_token(client)
    seeker_id, seeker_token = await create_user_and_token(client)
    stranger_id, stranger_token = await create_user_and_token(client)
    
    # Create listing and conversation
    listing_id = await create_listing(client, owner_token)
    
    seeker_headers = {"Authorization": f"Bearer {seeker_token}"}
    conv_data = {"listing_id": listing_id, "recipient_id": owner_id}
    response = await client.post("/api/v1/conversations", json=conv_data, headers=seeker_headers)
    
    # Get lead ID
    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    response = await client.get("/api/v1/leads", headers=owner_headers)
    leads = response.json()
    lead_id = leads[0]["id"]
    
    # Stranger tries to update lead
    stranger_headers = {"Authorization": f"Bearer {stranger_token}"}
    update_data = {"status": "contacted"}
    response = await client.patch(
        f"/api/v1/leads/{lead_id}/status",
        json=update_data,
        headers=stranger_headers
    )
    assert response.status_code == 403
    
    # Owner can update
    response = await client.patch(
        f"/api/v1/leads/{lead_id}/status",
        json=update_data,
        headers=owner_headers
    )
    assert response.status_code == 200
    
    # Seeker can also update
    update_data = {"status": "qualified"}
    response = await client.patch(
        f"/api/v1/leads/{lead_id}/status",
        json=update_data,
        headers=seeker_headers
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_owner_vs_seeker_lead_views(client: AsyncClient):
    """Test that owners and seekers see different perspectives of leads."""
    # Create owner and multiple seekers
    owner_id, owner_token = await create_user_and_token(client)
    seeker1_id, seeker1_token = await create_user_and_token(client)
    seeker2_id, seeker2_token = await create_user_and_token(client)
    another_owner_id, another_owner_token = await create_user_and_token(client)
    
    # Owner creates listing
    listing_id = await create_listing(client, owner_token)
    
    # Another owner creates their own listing
    another_listing_id = await create_listing(client, another_owner_token)
    
    # Seeker 1 contacts first owner's listing
    seeker1_headers = {"Authorization": f"Bearer {seeker1_token}"}
    conv_data = {"listing_id": listing_id, "recipient_id": owner_id}
    await client.post("/api/v1/conversations", json=conv_data, headers=seeker1_headers)
    
    # Seeker 1 also contacts another owner's listing
    conv_data = {"listing_id": another_listing_id, "recipient_id": another_owner_id}
    await client.post("/api/v1/conversations", json=conv_data, headers=seeker1_headers)
    
    # Seeker 2 contacts first owner's listing
    seeker2_headers = {"Authorization": f"Bearer {seeker2_token}"}
    conv_data = {"listing_id": listing_id, "recipient_id": owner_id}
    await client.post("/api/v1/conversations", json=conv_data, headers=seeker2_headers)
    
    # Owner sees incoming leads for their listing
    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    response = await client.get("/api/v1/leads", headers=owner_headers)
    assert response.status_code == 200
    owner_leads = response.json()
    
    # Should see leads from both seekers
    owner_seeker_ids = [l["seeker_id"] for l in owner_leads]
    assert seeker1_id in owner_seeker_ids
    assert seeker2_id in owner_seeker_ids
    
    # Seeker 1 sees outgoing leads
    response = await client.get("/api/v1/leads", headers=seeker1_headers)
    assert response.status_code == 200
    seeker1_leads = response.json()
    
    # Should see leads for both listings they contacted
    seeker1_listing_ids = [l["listing_id"] for l in seeker1_leads]
    assert listing_id in seeker1_listing_ids
    assert another_listing_id in seeker1_listing_ids
