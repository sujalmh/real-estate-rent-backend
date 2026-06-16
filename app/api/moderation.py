"""Moderation API endpoints for admin operations."""

import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.core.dependencies import get_current_admin
from app.database import get_db
from app.models.user import User
from app.models.listing import Listing
from app.schemas.moderation import ModerationQueueItem, ListingRejection
from app.schemas.listing import ListingResponse

router = APIRouter(prefix="/api/v1/admin", tags=["moderation"])


@router.get("/moderation/queue", response_model=List[ModerationQueueItem])
async def get_moderation_queue(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Get listings pending moderation.
    
    - Requires admin role
    - Returns listings with moderation_status='pending'
    - Ordered by creation date (oldest first)
    - Includes owner name for context
    """
    # Query pending listings
    result = await db.execute(
        select(Listing)
        .where(Listing.moderation_status == "pending")
        .order_by(Listing.created_at.asc())
        .offset(offset)
        .limit(limit)
    )
    listings = result.scalars().all()
    
    # Build responses with owner info
    queue_items = []
    for listing in listings:
        # Get owner info
        owner_result = await db.execute(
            select(User).where(User.id == listing.owner_id)
        )
        owner = owner_result.scalar_one_or_none()
        owner_name = owner.name if owner else "Unknown"
        
        queue_items.append(ModerationQueueItem(
            id=listing.id,
            title=listing.title,
            type=listing.type,
            owner_id=listing.owner_id,
            owner_name=owner_name,
            price_amount=listing.price_amount,
            city=listing.city,
            created_at=listing.created_at,
            moderation_status=listing.moderation_status
        ))
    
    return queue_items


@router.post("/listings/{listing_id}/approve", response_model=ListingResponse)
async def approve_listing(
    listing_id: uuid.UUID,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Approve a listing.
    
    - Requires admin role
    - Updates moderation_status to 'approved'
    - Updates status to 'active'
    - Listing becomes visible in search
    """
    # Get listing with owner
    result = await db.execute(
        select(Listing)
        .options(joinedload(Listing.owner))
        .where(Listing.id == listing_id)
    )
    listing = result.scalar_one_or_none()
    
    if not listing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Listing not found"
        )
    
    # Update moderation status
    listing.moderation_status = "approved"
    listing.status = "active"
    listing.rejection_reason = None  # Clear any previous rejection reason
    
    await db.commit()
    await db.refresh(listing)
    
    return listing


@router.post("/listings/{listing_id}/reject", response_model=ListingResponse)
async def reject_listing(
    listing_id: uuid.UUID,
    rejection_data: ListingRejection,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Reject a listing with a reason.
    
    - Requires admin role
    - Updates moderation_status to 'rejected'
    - Updates status to 'deleted'
    - Stores rejection reason
    - Listing becomes hidden from search
    """
    # Get listing with owner
    result = await db.execute(
        select(Listing)
        .options(joinedload(Listing.owner))
        .where(Listing.id == listing_id)
    )
    listing = result.scalar_one_or_none()
    
    if not listing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Listing not found"
        )
    
    # Update moderation status
    listing.moderation_status = "rejected"
    listing.status = "deleted"
    listing.rejection_reason = rejection_data.reason
    
    await db.commit()
    await db.refresh(listing)
    
    return listing
