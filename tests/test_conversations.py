"""Tests for conversation and messaging functionality."""

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
    listing_id = response.json()["id"]
    
    # Approve listing manually (simulate admin approval)
    # For testing, we'll just use it as is
    return listing_id


@pytest.mark.asyncio
async def test_create_conversation(client: AsyncClient):
    """Test creating a conversation between two users."""
    # Create owner user
    owner_id, owner_token = await create_user_and_token(client)
    
    # Create seeker user
    seeker_id, seeker_token = await create_user_and_token(client)
    
    # Owner creates a listing
    listing_id = await create_listing(client, owner_token)
    
    # Seeker creates a conversation
    seeker_headers = {"Authorization": f"Bearer {seeker_token}"}
    conv_data = {
        "listing_id": listing_id,
        "recipient_id": owner_id
    }
    
    response = await client.post("/api/v1/conversations", json=conv_data, headers=seeker_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["listing_id"] == listing_id
    assert data["initiator_id"] == seeker_id
    assert data["recipient_id"] == owner_id
    conversation_id = data["id"]
    
    # Verify conversation is accessible to both participants
    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    response = await client.get(f"/api/v1/conversations/{conversation_id}", headers=owner_headers)
    assert response.status_code == 200
    
    response = await client.get(f"/api/v1/conversations/{conversation_id}", headers=seeker_headers)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_prevent_duplicate_conversations(client: AsyncClient):
    """Test that creating duplicate conversations returns the existing one."""
    # Create owner and seeker
    owner_id, owner_token = await create_user_and_token(client)
    seeker_id, seeker_token = await create_user_and_token(client)
    
    # Owner creates a listing
    listing_id = await create_listing(client, owner_token)
    
    # Seeker creates first conversation
    seeker_headers = {"Authorization": f"Bearer {seeker_token}"}
    conv_data = {
        "listing_id": listing_id,
        "recipient_id": owner_id
    }
    
    response1 = await client.post("/api/v1/conversations", json=conv_data, headers=seeker_headers)
    assert response1.status_code == 201
    conv_id_1 = response1.json()["id"]
    
    # Seeker tries to create duplicate conversation
    response2 = await client.post("/api/v1/conversations", json=conv_data, headers=seeker_headers)
    assert response2.status_code == 201
    conv_id_2 = response2.json()["id"]
    
    # Should return the same conversation
    assert conv_id_1 == conv_id_2


@pytest.mark.asyncio
async def test_send_and_receive_messages(client: AsyncClient):
    """Test sending and receiving messages in a conversation."""
    # Create owner and seeker
    owner_id, owner_token = await create_user_and_token(client)
    seeker_id, seeker_token = await create_user_and_token(client)
    
    # Create listing and conversation
    listing_id = await create_listing(client, owner_token)
    
    seeker_headers = {"Authorization": f"Bearer {seeker_token}"}
    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    
    conv_data = {"listing_id": listing_id, "recipient_id": owner_id}
    response = await client.post("/api/v1/conversations", json=conv_data, headers=seeker_headers)
    conversation_id = response.json()["id"]
    
    # Seeker sends a message
    message_data = {"content": "Is this property still available?"}
    response = await client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json=message_data,
        headers=seeker_headers
    )
    assert response.status_code == 201
    message = response.json()
    assert message["content"] == message_data["content"]
    assert message["sender_id"] == seeker_id
    assert message["is_read"] == False
    
    # Owner gets messages (which marks them as read)
    response = await client.get(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=owner_headers
    )
    assert response.status_code == 200
    messages = response.json()
    assert len(messages) == 1
    assert messages[0]["content"] == message_data["content"]
    assert messages[0]["is_read"] == True  # Automatically marked as read
    
    # Owner sends a reply
    reply_data = {"content": "Yes, it is! Would you like to schedule a viewing?"}
    response = await client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json=reply_data,
        headers=owner_headers
    )
    assert response.status_code == 201
    
    # Seeker gets all messages
    response = await client.get(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=seeker_headers
    )
    assert response.status_code == 200
    messages = response.json()
    assert len(messages) == 2


@pytest.mark.asyncio
async def test_message_length_validation(client: AsyncClient):
    """Test that message content is validated (max 2000 chars)."""
    # Create users and conversation
    owner_id, owner_token = await create_user_and_token(client)
    seeker_id, seeker_token = await create_user_and_token(client)
    
    listing_id = await create_listing(client, owner_token)
    
    seeker_headers = {"Authorization": f"Bearer {seeker_token}"}
    conv_data = {"listing_id": listing_id, "recipient_id": owner_id}
    response = await client.post("/api/v1/conversations", json=conv_data, headers=seeker_headers)
    conversation_id = response.json()["id"]
    
    # Try to send message that's too long
    long_message = "a" * 2001
    message_data = {"content": long_message}
    response = await client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json=message_data,
        headers=seeker_headers
    )
    assert response.status_code == 422  # Validation error
    
    # Send valid message
    valid_message = "a" * 2000
    message_data = {"content": valid_message}
    response = await client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json=message_data,
        headers=seeker_headers
    )
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_conversation_permissions(client: AsyncClient):
    """Test that non-participants cannot access conversations."""
    # Create three users
    owner_id, owner_token = await create_user_and_token(client)
    seeker_id, seeker_token = await create_user_and_token(client)
    stranger_id, stranger_token = await create_user_and_token(client)
    
    # Create conversation between owner and seeker
    listing_id = await create_listing(client, owner_token)
    
    seeker_headers = {"Authorization": f"Bearer {seeker_token}"}
    stranger_headers = {"Authorization": f"Bearer {stranger_token}"}
    
    conv_data = {"listing_id": listing_id, "recipient_id": owner_id}
    response = await client.post("/api/v1/conversations", json=conv_data, headers=seeker_headers)
    conversation_id = response.json()["id"]
    
    # Stranger tries to access conversation
    response = await client.get(
        f"/api/v1/conversations/{conversation_id}",
        headers=stranger_headers
    )
    assert response.status_code == 403
    
    # Stranger tries to send message
    message_data = {"content": "Hello"}
    response = await client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json=message_data,
        headers=stranger_headers
    )
    assert response.status_code == 403
    
    # Stranger tries to get messages
    response = await client.get(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=stranger_headers
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_conversations(client: AsyncClient):
    """Test listing user's conversations."""
    # Create users
    owner_id, owner_token = await create_user_and_token(client)
    seeker1_id, seeker1_token = await create_user_and_token(client)
    seeker2_id, seeker2_token = await create_user_and_token(client)
    
    # Owner creates multiple listings
    listing1_id = await create_listing(client, owner_token)
    listing2_id = await create_listing(client, owner_token)
    
    # Seeker 1 creates conversation for listing 1
    seeker1_headers = {"Authorization": f"Bearer {seeker1_token}"}
    conv_data = {"listing_id": listing1_id, "recipient_id": owner_id}
    await client.post("/api/v1/conversations", json=conv_data, headers=seeker1_headers)
    
    # Seeker 2 creates conversation for listing 2
    seeker2_headers = {"Authorization": f"Bearer {seeker2_token}"}
    conv_data = {"listing_id": listing2_id, "recipient_id": owner_id}
    await client.post("/api/v1/conversations", json=conv_data, headers=seeker2_headers)
    
    # Owner lists conversations
    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    response = await client.get("/api/v1/conversations", headers=owner_headers)
    assert response.status_code == 200
    conversations = response.json()
    assert len(conversations) >= 2
    
    # Seeker 1 lists conversations
    response = await client.get("/api/v1/conversations", headers=seeker1_headers)
    assert response.status_code == 200
    conversations = response.json()
    assert len(conversations) >= 1


@pytest.mark.asyncio
async def test_mark_conversation_read(client: AsyncClient):
    """Test marking all messages in a conversation as read."""
    # Create owner and seeker
    owner_id, owner_token = await create_user_and_token(client)
    seeker_id, seeker_token = await create_user_and_token(client)
    
    # Create listing and conversation
    listing_id = await create_listing(client, owner_token)
    
    seeker_headers = {"Authorization": f"Bearer {seeker_token}"}
    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    
    conv_data = {"listing_id": listing_id, "recipient_id": owner_id}
    response = await client.post("/api/v1/conversations", json=conv_data, headers=seeker_headers)
    conversation_id = response.json()["id"]
    
    # Seeker sends multiple messages
    for i in range(3):
        await client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            json={"content": f"Message {i}"},
            headers=seeker_headers
        )
    
    # Verify owner has 3 unread messages
    response = await client.get(f"/api/v1/conversations/{conversation_id}", headers=owner_headers)
    assert response.json()["unread_count"] == 3
    
    # Owner marks conversation as read
    response = await client.patch(
        f"/api/v1/conversations/{conversation_id}/read",
        headers=owner_headers
    )
    assert response.status_code == 204
    
    # Verify owner now has 0 unread messages
    response = await client.get(f"/api/v1/conversations/{conversation_id}", headers=owner_headers)
    assert response.json()["unread_count"] == 0
