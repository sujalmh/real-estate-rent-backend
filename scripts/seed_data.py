#!/usr/bin/env python3
"""Script to seed the database with test data."""

import asyncio
import sys
import random
import uuid
from datetime import datetime, timedelta
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from sqlalchemy import select, delete
from app.database import async_session_maker
from app.models.user import User
from app.models.listing import Listing
from app.models.conversation import Conversation, Message
from app.models.supporting import Lead, Bookmark
from app.core.security import hash_password

# Constants
PASSWORD = "Password@123"
IMAGES = [
    "https://picsum.photos/id/10/800/600",
    "https://picsum.photos/id/11/800/600",
    "https://picsum.photos/id/12/800/600",
    "https://picsum.photos/id/13/800/600",
    "https://picsum.photos/id/14/800/600",
    "https://picsum.photos/id/15/800/600",
    "https://picsum.photos/id/16/800/600",
    "https://picsum.photos/id/17/800/600",
]

CITY_DATA = {
    "Mumbai": {"state": "Maharashtra", "lat": 19.0760, "lon": 72.8777},
    "Delhi": {"state": "Delhi", "lat": 28.7041, "lon": 77.1025},
    "Bangalore": {"state": "Karnataka", "lat": 12.9716, "lon": 77.5946},
    "Hyderabad": {"state": "Telangana", "lat": 17.3850, "lon": 78.4867},
    "Pune": {"state": "Maharashtra", "lat": 18.5204, "lon": 73.8567},
    "Chennai": {"state": "Tamil Nadu", "lat": 13.0827, "lon": 80.2707},
}

async def seed_data():
    """Seed database with test data."""
    async with async_session_maker() as db:
        print("🌱 Starting database seed...")

        # 0. Clear existing data
        print("Cleaning up existing data...")
        await db.execute(delete(Message))
        await db.execute(delete(Lead))
        await db.execute(delete(Bookmark))
        await db.execute(delete(Conversation))
        await db.execute(delete(Listing))
        await db.execute(delete(User))
        await db.commit()
        print("✓ Cleared all data")

        # 1. Create Users
        users = []
        roles_map = {0: ["owner", "seeker"], 1: ["owner"], 2: ["seeker"], 3: ["seeker"]}
        
        print("Creating users...")
        for i in range(4):
            email = f"user{i+1}@test.com"
            phone = f"+91987654321{i}"
            
            user = User(
                email=email,
                phone=phone,
                password_hash=hash_password(PASSWORD),
                name=f"Test User {i+1}",
                roles=roles_map.get(i, ["seeker"]),
                verified=True,
                status="active"
            )
            db.add(user)
            users.append(user)
        
        await db.commit()
        for u in users: await db.refresh(u)
        print(f"✓ Created {len(users)} users")

        # Split into owners and seekers
        owners = [u for u in users if "owner" in u.roles]
        seekers = [u for u in users if "seeker" in u.roles]

        # 2. Create Listings
        listings = []
        listing_types = ["rental", "sale", "pg"]
        property_types = ["apartment", "house", "villa"]
        
        print("Creating listings...")
        for owner in owners:
            for i in range(3): # 3 listings per owner
                city_name = random.choice(list(CITY_DATA.keys()))
                city_info = CITY_DATA[city_name]
                
                # Generate random variation for coordinates (approx 5km radius)
                # 1 degree approx 111km. 0.05 degrees approx 5.5km
                lat_offset = random.uniform(-0.05, 0.05)
                lon_offset = random.uniform(-0.05, 0.05)
                
                title = f"{random.choice(property_types).title()} in {city_name} - {i+1}"
                
                listing = Listing(
                    owner_id=owner.id,
                    title=title,
                    description=f"Beautiful {title.lower()} with great amenities. Close to public transport and markets.",
                    type=random.choice(listing_types),
                    status="active",
                    moderation_status="approved",  # Auto-approve for seed data
                    price_amount=random.randint(10000, 5000000),
                    price_currency="INR",
                    price_type="monthly" if random.random() > 0.5 else "sale",
                    address=f"Street {random.randint(1, 20)}, Sector {random.randint(1, 100)}",
                    city=city_name,
                    state=city_info["state"],
                    country="India",
                    postal_code=f"4000{random.randint(10, 99)}",
                    latitude=city_info["lat"] + lat_offset,
                    longitude=city_info["lon"] + lon_offset,
                    size=random.randint(500, 3000),
                    amenities=["wifi", "parking", "ac", "gym"] if random.random() > 0.5 else ["parking"],
                    images=[
                        {"url": random.choice(IMAGES), "order": 0, "is_primary": True},
                        {"url": random.choice(IMAGES), "order": 1, "is_primary": False}
                    ],
                    view_count=random.randint(0, 100),
                    lead_count=0
                )
                db.add(listing)
                listings.append(listing)
        
        await db.commit()
        for l in listings: await db.refresh(l)
        print(f"✓ Created {len(listings)} listings")

        # 3. Create Conversations & Messages
        print("Creating conversations...")
        conversations = []
        
        # each seeker starts conversation with random listing owner
        for seeker in seekers:
            # Pick a listing not owned by seeker
            valid_listings = [l for l in listings if l.owner_id != seeker.id]
            if not valid_listings: continue
            
            target_listing = random.choice(valid_listings)
            owner_id = target_listing.owner_id
            
            # Check existing
            participants = sorted([seeker.id, owner_id])
            
            conv = Conversation(
                listing_id=target_listing.id,
                participants=participants,
                last_message_at=datetime.utcnow()
            )
            db.add(conv)
            await db.flush() # get ID
            
            conversations.append(conv)
            
            # Create Lead
            lead = Lead(
                listing_id=target_listing.id,
                seeker_id=seeker.id,
                owner_id=owner_id,
                conversation_id=conv.id,
                status="new"
            )
            db.add(lead)
            
            # Update lead count
            target_listing.lead_count += 1
            
            # Add Messages
            msgs = [
                ("Hi, is this still available?", seeker.id),
                ("Yes, it is!", owner_id),
                ("When can I visit?", seeker.id),
                ("How about tomorrow at 5 PM?", owner_id)
            ]
            
            for i, (content, sender_id) in enumerate(msgs):
                msg = Message(
                    conversation_id=conv.id,
                    sender_id=sender_id,
                    content=content,
                    sent_at=datetime.utcnow() - timedelta(minutes=10 - i),
                    read_at=datetime.utcnow() if i < 2 else None # last 2 unread
                )
                db.add(msg)
                
        await db.commit()
        print(f"✓ Created {len(conversations)} conversations with messages")

        # 4. Create Bookmarks
        print("Creating bookmarks...")
        for seeker in seekers:
            # Bookmark random listings
            targets = random.sample(listings, min(len(listings), 3))
            for t in targets:
                # Check duplication if needed, but assuming fresh enough
                b = Bookmark(
                    user_id=seeker.id,
                    listing_id=t.id
                )
                db.add(b)
                
        await db.commit()
        print("✓ Created bookmarks")

        print("\n✅ Seed completed successfully!")
        print("Test Users:")
        for u in users:
            print(f"  {u.email} / {PASSWORD} ({u.roles})")

if __name__ == "__main__":
    asyncio.run(seed_data())
