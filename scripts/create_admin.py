#!/usr/bin/env python3
"""Script to create an admin user for testing."""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from sqlalchemy import select
from app.database import async_session_maker
from app.models.user import User
from app.core.security import hash_password


async def create_admin_user():
    """Create admin user if it doesn't exist."""
    async with async_session_maker() as db:
        # Check if admin user already exists
        result = await db.execute(
            select(User).where(User.email == "admin@realestate.com")
        )
        existing_admin = result.scalar_one_or_none()
        
        if existing_admin:
            print("✓ Admin user already exists")
            print(f"  Email: {existing_admin.email}")
            print(f"  Roles: {existing_admin.roles}")
            return
        
        # Create admin user
        admin_password = "Admin@123"  # Should be changed after first login
        admin_user = User(
            email="admin@realestate.com",
            phone="+919999999999",
            password_hash=hash_password(admin_password),
            name="Platform Administrator",
            roles=["admin", "seeker"],
            verified=True,
            status="active"
        )
        
        db.add(admin_user)
        await db.commit()
        await db.refresh(admin_user)
        
        print("✓ Admin user created successfully!")
        print(f"  Email: {admin_user.email}")
        print(f"  Password: {admin_password}")
        print(f"  Roles: {admin_user.roles}")
        print("\n⚠️  Please change the password after first login")


if __name__ == "__main__":
    asyncio.run(create_admin_user())
