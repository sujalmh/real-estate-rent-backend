
import pytest
import uuid
from httpx import AsyncClient
from faker import Faker
from sqlalchemy import text

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
async def test_explicit_sort(client: AsyncClient, db_session):
    """Test explicit sort options (Price)."""
    token = await create_user_and_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    
    # Create 3 listings with specific prices
    prices = [10000, 5000, 20000]
    ids = []
    
    for p in prices:
        resp = await client.post("/api/v1/listings", json={
            "type": "rental", "title": f"Rent {p}", "price_amount": p, "city": "SortCity"
        }, headers=headers)
        ids.append(resp.json()["id"])
        
    # Approve them
    ids_str = "', '".join(ids)
    await db_session.execute(text(f"UPDATE listings SET status='active', moderation_status='approved' WHERE id IN ('{ids_str}')"))
    await db_session.commit()
    
    # 1. Sort Price ASC (Low to High) -> 5000, 10000, 20000
    resp = await client.post("/api/v1/search/listings", json={
        "filters": {"city": "SortCity"},
        "sort": "price_asc"
    })
    items = resp.json()["items"]
    assert len(items) == 3
    assert float(items[0]["price_amount"]) == 5000.0
    assert float(items[1]["price_amount"]) == 10000.0
    assert float(items[2]["price_amount"]) == 20000.0
    
    # 2. Sort Price DESC (High to Low) -> 20000, 10000, 5000
    resp = await client.post("/api/v1/search/listings", json={
        "filters": {"city": "SortCity"},
        "sort": "price_desc"
    })
    items = resp.json()["items"]
    assert len(items) == 3
    assert float(items[0]["price_amount"]) == 20000.0
    assert float(items[1]["price_amount"]) == 10000.0
    assert float(items[2]["price_amount"]) == 5000.0
