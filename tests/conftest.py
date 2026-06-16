"""Test configuration and fixtures."""

import asyncio
from typing import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.main import app
from app.database import Base, get_db
from app.config import get_settings

settings = get_settings()

# Test database URL
TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/real_estate_test_db"


@pytest_asyncio.fixture(scope="function")
async def engine():
    """Create a fresh database engine for each test."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        pool_pre_ping=True,
    )
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a fresh database session for each test."""
    from sqlalchemy import text
    
    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        await conn.run_sync(Base.metadata.create_all)

    # Create session
    session_maker = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_maker() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create a test client with database session override."""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    from httpx import ASGITransport
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture(scope="function")
async def admin_user(db_session: AsyncSession):
    """Create an admin user for testing."""
    from app.models.user import User
    from app.core.security import hash_password
    
    admin = User(
        email="admin@realestate.com",
        phone="+919999999999",
        password_hash=hash_password("Admin@123"),
        name="Platform Administrator",
        roles=["admin", "seeker"],
        verified=True,
        status="active"
    )
    
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)
    
    return admin
