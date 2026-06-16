"""End-to-End Integration Tests for Real Estate Platform."""

import pytest
import uuid
from httpx import AsyncClient
from faker import Faker

fake = Faker()


async def create_new_user(client: AsyncClient, role: str = "seeker"):
    """Helper to register and login a new user."""
    uid = str(uuid.uuid4())[:8]
    user_data = {
        "email": f"{role}_{uid}_{fake.first_name().lower()}@{fake.domain_name()}",
        "phone": f"+1{str(int(uuid.uuid4()))[-10:]}",
        "name": fake.name(),
        "password": f"Strong{uid}!",
        "role": role  # note: registration endpoint might not take role directly depending on implementation, 
                      # but for this test we'll assume default is seeker, or we might need to update db if we want specific roles.
                      # Based on User model, roles is a list. Let's check registration endpoint behavior if needed.
                      # For now, default registration usually creates 'seeker'.
    }
    
    # Register
    # Note: If our API doesn't allow setting role on registration (common security practice),
    # we might need to rely on default 'seeker' or update DB manually for 'owner' if needed.
    # Looking at User model, roles default is ["seeker"].
    # Effectively anyone can list, so specific 'owner' role might not be strictly enforced for creation,
    # but let's stick to the flow.
    
    resp = await client.post("/api/v1/users/register", json=user_data)
    assert resp.status_code == 201
    user_id = resp.json()["id"]
    
    # Login
    login_data = {"email": user_data["email"], "password": user_data["password"]}
    resp = await client.post("/api/v1/auth/login", json=login_data)
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    
    return {"id": user_id, "token": token, "headers": {"Authorization": f"Bearer {token}"}}


@pytest.mark.asyncio
async def test_complete_user_journey(client: AsyncClient, admin_user):
    """
    Test the complete flow:
    1. Register Owner & Seeker
    2. Owner creates listing
    3. Admin approves listing
    4. Seeker searches and finds listing
    5. Seeker bookmarks listing
    6. Seeker messages Owner (creating lead)
    7. Owner sees lead and replies
    """
    
    # 1. Registration
    owner = await create_new_user(client, role="owner")
    seeker = await create_new_user(client, role="seeker")
    
    # Get Admin Token
    admin_login = {"email": "admin@realestate.com", "password": "Admin@123"}
    resp = await client.post("/api/v1/auth/login", json=admin_login)
    assert resp.status_code == 200
    admin_token = resp.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # 2. Owner creates listing
    listing_data = {
        "type": "rental",
        "title": f"Luxury Apartment {uuid.uuid4()}",
        "description": "A beautiful place to stay",
        "price_amount": 2500.00,
        "city": "Metropolis",
        "country": "India",
        "amenities": ["wifi", "parking"]
    }
    resp = await client.post("/api/v1/listings", json=listing_data, headers=owner["headers"])
    assert resp.status_code == 201
    listing_id = resp.json()["id"]
    
    # Verify not yet in search (pending moderation)
    resp = await client.post("/api/v1/search/listings", json={"filters": {"city": "Metropolis"}})
    assert resp.status_code == 200
    found_ids = [item["id"] for item in resp.json()["items"]]
    assert listing_id not in found_ids

    # 3. Admin approves listing
    resp = await client.post(f"/api/v1/admin/listings/{listing_id}/approve", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["moderation_status"] == "approved"

    # 4. Search visibility
    resp = await client.post("/api/v1/search/listings", json={"filters": {"city": "Metropolis"}})
    assert resp.status_code == 200
    found_ids = [item["id"] for item in resp.json()["items"]]
    assert listing_id in found_ids

    # 5. Seeker bookmarks listing
    resp = await client.post("/api/v1/bookmarks", json={"listing_id": listing_id}, headers=seeker["headers"])
    assert resp.status_code == 201
    
    # Verify bookmark list
    resp = await client.get("/api/v1/bookmarks", headers=seeker["headers"])
    assert resp.status_code == 200
    bookmarked_ids = [item["listing_id"] for item in resp.json()["items"]]
    assert listing_id in bookmarked_ids

    # 6. Seeker starts conversation
    # We can assume starting a conversation is implicit via sending a message or explicit create
    # Based on Phase 5, we have create conversation endpoint.
    conv_data = {"listing_id": listing_id, "recipient_id": owner["id"]}
    resp = await client.post("/api/v1/conversations", json=conv_data, headers=seeker["headers"])
    assert resp.status_code == 201
    conversation_id = resp.json()["id"]
    
    # Seeker sends message
    msg_data = {"content": "Is this apartment available?"}
    resp = await client.post(f"/api/v1/conversations/{conversation_id}/messages", json=msg_data, headers=seeker["headers"])
    assert resp.status_code == 201

    # 7. Owner checks leads
    resp = await client.get("/api/v1/leads?status=new", headers=owner["headers"])
    assert resp.status_code == 200
    leads = resp.json()
    assert len(leads) > 0
    # Find lead for this listing
    lead = next((l for l in leads if l["listing_id"] == listing_id), None)
    assert lead is not None
    assert lead["seeker_id"] == seeker["id"]
    
    # Owner replies
    # Owner gets conversation from lead or list
    resp = await client.get(f"/api/v1/conversations/{conversation_id}/messages", headers=owner["headers"])
    assert resp.status_code == 200
    
    reply_data = {"content": "Yes, it is available!"}
    resp = await client.post(f"/api/v1/conversations/{conversation_id}/messages", json=reply_data, headers=owner["headers"])
    assert resp.status_code == 201

    # Final verification: Check Seeker received reply
    resp = await client.get(f"/api/v1/conversations/{conversation_id}/messages", headers=seeker["headers"])
    messages = resp.json()
    assert len(messages) == 2
    assert messages[1]["content"] == "Yes, it is available!"
    assert messages[1]["sender_id"] == owner["id"]


@pytest.mark.asyncio
async def test_error_handling_scenarios(client: AsyncClient, admin_user):
    """Test various error handling scenarios."""
    user = await create_new_user(client)
    
    # 1. Invalid Authentication
    # Use a protected endpoint that requires authentication (logout)
    resp = await client.post("/api/v1/auth/logout", headers={"Authorization": "Bearer invalid_token"})
    assert resp.status_code == 401
    
    # 2. Not Found Error
    fake_id = str(uuid.uuid4())
    resp = await client.get(f"/api/v1/listings/{fake_id}", headers=user["headers"])
    assert resp.status_code == 404
    
    # 3. Validation Error (Create listing with missing fields)
    invalid_listing = {"title": "Missing Price"} # Missing price, type, etc.
    resp = await client.post("/api/v1/listings", json=invalid_listing, headers=user["headers"])
    assert resp.status_code == 422
    
    # 4. Unauthorized Access (Edit another user's listing)
    # Create another user and their listing
    other_user = await create_new_user(client)
    listing_data = {
        "type": "rental",
        "title": "Other's Place",
        "price_amount": 1000.00,
        "city": "Gotham", 
        "country": "India"
    }
    resp = await client.post("/api/v1/listings", json=listing_data, headers=other_user["headers"])
    listing_id = resp.json()["id"]
    
    # Try to delete with first user
    resp = await client.delete(f"/api/v1/listings/{listing_id}", headers=user["headers"])
    assert resp.status_code in [403, 404] # Depending on implementation (404 if filtered by owner, 403 if check exists)
