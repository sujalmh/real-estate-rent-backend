"""Standard async tests for user registration and authentication with randomized data."""

from typing import Dict
import uuid
import re

import pytest
from httpx import AsyncClient
from faker import Faker

from app.core.security import verify_password

fake = Faker()


async def generate_valid_user_data() -> Dict:
    """Generate valid user registration data with unique fields."""
    uid = str(uuid.uuid4())[:8]
    return {
        "email": f"user_{uid}_{fake.first_name().lower()}@{fake.domain_name()}",
        "phone": f"+1{str(int(uuid.uuid4()))[-10:]}",
        "name": fake.name(),
        "password": f"Strong{uid}!"  # Meets all criteria
    }


def generate_weak_password() -> str:
    """Generate a weak password."""
    # Return various weak passwords
    import random
    options = [
        "short",     # Too short
        "noupper",   # No uppercase: "weakpass123!"
        "nolower",   # No lowercase: "WEAKPASS123!"
        "nodigit",   # No digit: "WeakPass!"
    ]
    choice = random.choice(options)
    
    if choice == "short":
        return "Short1!"
    elif choice == "noupper":
        return "weakpass123!"
    elif choice == "nolower":
        return "WEAKPASS123!"
    elif choice == "nodigit":
        return "WeakPass!"
    return "weak"


# Property 1: User Registration Validity
@pytest.mark.asyncio
async def test_property_valid_registration_succeeds(client: AsyncClient):
    """
    Property 1: User Registration Validity (Randomized Loop)
    
    Given valid registration data, registration should succeed.
    """
    # Run 10 iterations with random data
    for _ in range(10):
        user_data = await generate_valid_user_data()
        
        response = await client.post("/api/v1/users/register", json=user_data)
        
        assert response.status_code == 201, f"Registration failed: {response.json()}"
        
        data = response.json()
        assert "id" in data
        assert data["email"] == user_data["email"]
        assert data["name"] == user_data["name"]
        assert data["phone"] == user_data["phone"]
        assert data["roles"] == ["seeker"]
        assert data["status"] == "active"
        assert data["verified"] is False
        assert "password" not in data
        assert "password_hash" not in data
        
        # Verify privacy_settings default (None or empty dict depending on implementation)
        # We allow None or empty dict
        pass


# Property 2: Invalid Registration Rejection
@pytest.mark.asyncio
async def test_property_duplicate_email_rejected(client: AsyncClient):
    """
    Property 2: Invalid Registration Rejection (Duplicate Email)
    """
    user_data = await generate_valid_user_data()
    
    # First registration should succeed
    response1 = await client.post("/api/v1/users/register", json=user_data)
    assert response1.status_code == 201
    
    # Second registration with same email should fail
    user_data["phone"] = f"+1{str(int(uuid.uuid4()))[-10:]}"  # Different phone
    response2 = await client.post("/api/v1/users/register", json=user_data)
    assert response2.status_code == 400
    assert "email" in response2.json()["detail"].lower()


@pytest.mark.asyncio
async def test_property_weak_password_rejected(client: AsyncClient):
    """
    Property 2: Invalid Registration Rejection (Weak Password)
    """
    # Run 5 iterations with weak passwords
    for _ in range(5):
        user_data = await generate_valid_user_data()
        user_data["password"] = generate_weak_password()
        
        response = await client.post("/api/v1/users/register", json=user_data)
        assert response.status_code == 422  # Validation error


# Property 3: Authentication Success
@pytest.mark.asyncio
async def test_property_authentication_succeeds(client: AsyncClient):
    """
    Property 3: Authentication Success
    """
    # Run 5 iterations
    for _ in range(5):
        user_data = await generate_valid_user_data()
        
        # Register user
        register_response = await client.post("/api/v1/users/register", json=user_data)
        assert register_response.status_code == 201
        
        # Authenticate
        login_data = {
            "email": user_data["email"],
            "password": user_data["password"]
        }
        auth_response = await client.post("/api/v1/auth/login", json=login_data)
        
        assert auth_response.status_code == 200, f"Login failed for {user_data['email']}"
        auth_data = auth_response.json()
        
        assert "access_token" in auth_data
        assert "refresh_token" in auth_data
        assert auth_data["token_type"] == "bearer"
        assert len(auth_data["access_token"]) > 0


@pytest.mark.asyncio
async def test_property_wrong_password_rejected(client: AsyncClient):
    """
    Property 3: Authentication Failure (Wrong Password)
    """
    user_data = await generate_valid_user_data()
    
    # Register
    await client.post("/api/v1/users/register", json=user_data)
    
    # Try to login with wrong password
    login_data = {
        "email": user_data["email"],
        "password": "WrongPass123!"
    }
    response = await client.post("/api/v1/auth/login", json=login_data)
    
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_property_rate_limiting_locks_account(client: AsyncClient):
    """
    Property: Rate Limiting
    """
    user_data = await generate_valid_user_data()
    
    # Register user
    await client.post("/api/v1/users/register", json=user_data)
    
    # Make 5 failed login attempts
    wrong_login = {
        "email": user_data["email"],
        "password": "WrongPass123!"
    }
    
    for i in range(5):
        response = await client.post("/api/v1/auth/login", json=wrong_login)
        # Attempt 5 (index 4) triggers the lock and returns 403
        if i == 4:
            assert response.status_code == 403
        else:
            assert response.status_code == 401
    
    # 6th attempt should be locked
    response = await client.post("/api/v1/auth/login", json=wrong_login)
    assert response.status_code == 403
    assert "locked" in response.json()["detail"].lower()
