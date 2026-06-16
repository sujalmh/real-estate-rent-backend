"""Conversation management API endpoints."""

import uuid
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.models.listing import Listing
from app.models.conversation import Conversation, Message
from app.models.supporting import Lead
from app.schemas.conversation import ConversationCreate, ConversationResponse

router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])


@router.post("", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    conversation_data: ConversationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new conversation or return existing one.
    
    - Validates that listing exists and is active
    - Checks if conversation already exists between these users for this listing
    - If exists, returns existing conversation; if not, creates new one
    - Automatically creates a lead record when conversation is initiated
    """
    listing_id = conversation_data.listing_id
    recipient_id = conversation_data.recipient_id
    
    # Prevent self-messaging
    if recipient_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot create conversation with yourself"
        )
    
    # Verify listing exists and is active
    result = await db.execute(
        select(Listing).where(Listing.id == listing_id)
    )
    listing = result.scalar_one_or_none()
    
    if not listing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Listing not found"
        )
    
    # Allow conversations for active or pending listings
    if listing.status not in ["active", "pending_review"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot create conversation for inactive listing"
        )
    
    # Verify recipient exists
    result = await db.execute(
        select(User).where(User.id == recipient_id)
    )
    recipient = result.scalar_one_or_none()
    
    if not recipient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recipient not found"
        )
    
    # Check if conversation already exists
    # Sort UUIDs for consistent comparison
    participants = sorted([current_user.id, recipient_id])
    result = await db.execute(
        select(Conversation).where(
            and_(
                Conversation.listing_id == listing_id,
                Conversation.participants == participants
            )
        )
    )
    existing = result.scalar_one_or_none()
    
    if existing:
        # Return existing conversation
        # Participants are already UUID objects from the database
        parts = existing.participants
        
        return ConversationResponse(
            id=existing.id,
            listing_id=existing.listing_id,
            initiator_id=parts[0],
            recipient_id=parts[1],
            listing_title=listing.title,
            created_at=existing.created_at,
            updated_at=existing.last_message_at or existing.created_at,
            last_message_preview=None,
            unread_count=0
        )
    
    # Create new conversation with sorted participants for consistency
    new_conversation = Conversation(
        listing_id=listing_id,
        participants=participants
    )
    db.add(new_conversation)
    await db.flush()  # Get the ID without committing
    
    # Create lead record
    new_lead = Lead(
        listing_id=listing_id,
        seeker_id=current_user.id,
        owner_id=listing.owner_id,
        conversation_id=new_conversation.id,
        status="new"
    )
    db.add(new_lead)
    
    # Increment lead count on listing
    listing.lead_count += 1
    
    await db.commit()
    await db.refresh(new_conversation)
    
    return ConversationResponse(
        id=new_conversation.id,
        listing_id=new_conversation.listing_id,
        initiator_id=current_user.id,
        recipient_id=recipient_id,
        listing_title=listing.title,
        created_at=new_conversation.created_at,
        updated_at=new_conversation.created_at,
        last_message_preview=None,
        unread_count=0
    )


@router.get("", response_model=List[ConversationResponse])
async def list_conversations(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List all conversations for the authenticated user.
    
    - Includes last message preview and unread count
    - Ordered by most recent activity (last_message_at DESC)
    """
    # Query conversations where user is a participant
    # Use a raw SQL check instead of SQLAlchemy syntax for array contains
    from sqlalchemy import text
    
    result = await db.execute(
        select(Conversation)
        .where(text(":user_id = ANY(participants)"))
        .params(user_id=current_user.id)
        .order_by(
            func.coalesce(Conversation.last_message_at, Conversation.created_at).desc()
        )
        .offset(offset)
        .limit(limit)
    )
    conversations = result.scalars().all()
    
    # Build responses with listing info and unread counts
    responses = []
    for conv in conversations:
        # Get listing details
        listing_title = None
        if conv.listing_id:
            listing_result = await db.execute(
                select(Listing).where(Listing.id == conv.listing_id)
            )
            listing = listing_result.scalar_one_or_none()
            if listing:
                listing_title = listing.title
        
        # Get last message
        last_msg_result = await db.execute(
            select(Message)
            .where(Message.conversation_id == conv.id)
            .order_by(Message.sent_at.desc())
            .limit(1)
        )
        last_message = last_msg_result.scalar_one_or_none()
        last_message_preview = None
        if last_message and last_message.content:
            last_message_preview = last_message.content[:100]
        
        # Count unread messages (not sent by current user and not read)
        unread_result = await db.execute(
            select(func.count())
            .select_from(Message)
            .where(
                and_(
                    Message.conversation_id == conv.id,
                    Message.sender_id != current_user.id,
                    Message.read_at.is_(None)
                )
            )
        )
        unread_count = unread_result.scalar() or 0
        
        # Determine initiator and recipient (already UUID objects)
        parts = conv.participants
        
        responses.append(ConversationResponse(
            id=conv.id,
            listing_id=conv.listing_id,
            initiator_id=parts[0],
            recipient_id=parts[1],
            listing_title=listing_title,
            created_at=conv.created_at,
            updated_at=conv.last_message_at or conv.created_at,
            last_message_preview=last_message_preview,
            unread_count=unread_count
        ))
    
    return responses


@router.get("/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get details of a specific conversation.
    
    - Verifies user is a participant
    - Returns full conversation details
    """
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conv = result.scalar_one_or_none()
    
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )
    
    # Verify user is participant (participants are already UUID objects)
    participant_ids = conv.participants
    if current_user.id not in participant_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a participant in this conversation"
        )
    
    # Get listing details
    listing_title = None
    if conv.listing_id:
        listing_result = await db.execute(
            select(Listing).where(Listing.id == conv.listing_id)
        )
        listing = listing_result.scalar_one_or_none()
        if listing:
            listing_title = listing.title
    
    # Count unread messages
    unread_result = await db.execute(
        select(func.count())
        .select_from(Message)
        .where(
            and_(
                Message.conversation_id == conversation_id,
                Message.sender_id != current_user.id,
                Message.read_at.is_(None)
            )
        )
    )
    unread_count = unread_result.scalar() or 0
    
    return ConversationResponse(
        id=conv.id,
        listing_id=conv.listing_id,
        initiator_id=participant_ids[0],
        recipient_id=participant_ids[1],
        listing_title=listing_title,
        created_at=conv.created_at,
        updated_at=conv.last_message_at or conv.created_at,
        last_message_preview=None,
        unread_count=unread_count
    )


@router.patch("/{conversation_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_conversation_read(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Mark all messages in a conversation as read for the current user.
    """
    # Verify conversation exists and user is participant
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conv = result.scalar_one_or_none()
    
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )
    
    if current_user.id not in conv.participants:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a participant in this conversation"
        )
    
    # Update all unread messages sent to this user in this conversation
    from sqlalchemy import update
    from app.models.conversation import Message
    
    now = datetime.now()
    await db.execute(
        update(Message)
        .where(
            and_(
                Message.conversation_id == conversation_id,
                Message.sender_id != current_user.id,
                Message.read_at.is_(None)
            )
        )
        .values(read_at=now, status="read")
    )
    
    await db.commit()
    return None
