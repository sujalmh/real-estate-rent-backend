"""Lead management API endpoints."""

import uuid
from typing import List, Optional
from datetime import datetime, UTC

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from pydantic import BaseModel, ConfigDict

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.models.listing import Listing
from app.models.conversation import Conversation
from app.models.supporting import Lead

router = APIRouter(prefix="/api/v1/leads", tags=["leads"])


# Schemas
class LeadResponse(BaseModel):
    """Lead response schema."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    listing_id: uuid.UUID
    seeker_id: uuid.UUID
    owner_id: uuid.UUID
    conversation_id: Optional[uuid.UUID]
    status: str
    created_at: datetime
    updated_at: datetime
    # Additional info
    listing_title: Optional[str] = None
    seeker_name: Optional[str] = None
    owner_name: Optional[str] = None


class LeadStatusUpdate(BaseModel):
    """Schema for updating lead status."""
    status: str  # new, contacted, qualified, converted, lost


@router.get("", response_model=List[LeadResponse])
async def list_leads(
    status_filter: Optional[str] = Query(default=None, alias="status"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List leads for the authenticated user.
    
    - For owners: shows incoming leads (listings they own)
    - For seekers: shows outgoing leads (conversations they initiated)
    - Supports filtering by status
    """
    # Check if user is owner or seeker
    # Query leads where user is either the owner or the seeker
    query = select(Lead).where(
        or_(
            Lead.owner_id == current_user.id,
            Lead.seeker_id == current_user.id
        )
    )
    
    # Apply status filter if provided
    if status_filter:
        query = query.where(Lead.status == status_filter)
    
    # Apply pagination and ordering
    query = query.order_by(Lead.created_at.desc()).offset(offset).limit(limit)
    
    result = await db.execute(query)
    leads = result.scalars().all()
    
    # Build responses with additional info
    responses = []
    for lead in leads:
        # Get listing info
        listing_title = None
        listing_result = await db.execute(
            select(Listing).where(Listing.id == lead.listing_id)
        )
        listing = listing_result.scalar_one_or_none()
        if listing:
            listing_title = listing.title
        
        # Get seeker info
        seeker_name = None
        seeker_result = await db.execute(
            select(User).where(User.id == lead.seeker_id)
        )
        seeker = seeker_result.scalar_one_or_none()
        if seeker:
            seeker_name = seeker.name
        
        # Get owner info
        owner_name = None
        owner_result = await db.execute(
            select(User).where(User.id == lead.owner_id)
        )
        owner = owner_result.scalar_one_or_none()
        if owner:
            owner_name = owner.name
        
        responses.append(LeadResponse(
            id=lead.id,
            listing_id=lead.listing_id,
            seeker_id=lead.seeker_id,
            owner_id=lead.owner_id,
            conversation_id=lead.conversation_id,
            status=lead.status,
            created_at=lead.created_at,
            updated_at=lead.updated_at,
            listing_title=listing_title,
            seeker_name=seeker_name,
            owner_name=owner_name
        ))
    
    return responses


@router.patch("/{lead_id}/status", response_model=LeadResponse)
async def update_lead_status(
    lead_id: uuid.UUID,
    status_update: LeadStatusUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Update lead status.
    
    - Validates user has permission (owner of listing or initiator of lead)
    - Allowed statuses: new, contacted, qualified, converted, lost
    """
    # Get lead
    result = await db.execute(
        select(Lead).where(Lead.id == lead_id)
    )
    lead = result.scalar_one_or_none()
    
    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found"
        )
    
    # Verify user has permission
    if lead.owner_id != current_user.id and lead.seeker_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to update this lead"
        )
    
    # Validate status
    valid_statuses = ["new", "contacted", "qualified", "converted", "lost"]
    if status_update.status not in valid_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
        )
    
    # Update status
    lead.status = status_update.status
    lead.updated_at = datetime.now(UTC).replace(tzinfo=None)
    
    await db.commit()
    await db.refresh(lead)
    
    # Get additional info for response
    listing_title = None
    listing_result = await db.execute(
        select(Listing).where(Listing.id == lead.listing_id)
    )
    listing = listing_result.scalar_one_or_none()
    if listing:
        listing_title = listing.title
    
    seeker_name = None
    seeker_result = await db.execute(
        select(User).where(User.id == lead.seeker_id)
    )
    seeker = seeker_result.scalar_one_or_none()
    if seeker:
        seeker_name = seeker.name
    
    owner_name = None
    owner_result = await db.execute(
        select(User).where(User.id == lead.owner_id)
    )
    owner = owner_result.scalar_one_or_none()
    if owner:
        owner_name = owner.name
    
    return LeadResponse(
        id=lead.id,
        listing_id=lead.listing_id,
        seeker_id=lead.seeker_id,
        owner_id=lead.owner_id,
        conversation_id=lead.conversation_id,
        status=lead.status,
        created_at=lead.created_at,
        updated_at=lead.updated_at,
        listing_title=listing_title,
        seeker_name=seeker_name,
        owner_name=owner_name
    )
