"""Message management API endpoints."""

import uuid
from typing import List
from datetime import datetime, UTC

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.models.conversation import Conversation, Message
from app.schemas.message import MessageCreate, MessageResponse

router = APIRouter(prefix="/api/v1", tags=["messages"])


@router.post("/conversations/{conversation_id}/messages", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def send_message(
    conversation_id: uuid.UUID,
    message_data: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Send a message in a conversation.
    
    - Validates user is a participant
    - Validates message content (max 2000 chars)
    - Updates conversation's last_message_at timestamp
    """
    # Get conversation and verify user is participant
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conversation = result.scalar_one_or_none()
    
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )
    
    # Verify user is participant
    participant_ids = [uuid.UUID(str(p)) for p in conversation.participants]
    if current_user.id not in participant_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a participant in this conversation"
        )
    
    # Create message
    new_message = Message(
        conversation_id=conversation_id,
        sender_id=current_user.id,
        content=message_data.content,
        media_url=message_data.image_url,
        status="sent"
    )
    db.add(new_message)
    
    # Update conversation's last_message_at
    conversation.last_message_at = datetime.now(UTC).replace(tzinfo=None)
    
    await db.commit()
    await db.refresh(new_message)
    
    return MessageResponse(
        id=new_message.id,
        conversation_id=new_message.conversation_id,
        sender_id=new_message.sender_id,
        content=new_message.content,
        image_url=new_message.media_url,
        is_read=bool(new_message.read_at),
        created_at=new_message.sent_at
    )


@router.get("/conversations/{conversation_id}/messages", response_model=List[MessageResponse])
async def get_messages(
    conversation_id: uuid.UUID,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get all messages in a conversation (paginated).
    
    - Verifies user is a participant
    - Orders by creation time (sent_at ASC)
    - Automatically marks all unread messages as read for the authenticated user
    """
    # Get conversation and verify user is participant
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conversation = result.scalar_one_or_none()
    
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )
    
    # Verify user is participant
    participant_ids = [uuid.UUID(str(p)) for p in conversation.participants]
    if current_user.id not in participant_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a participant in this conversation"
        )
    
    # Get messages
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.sent_at.asc())
        .offset(offset)
        .limit(limit)
    )
    messages = result.scalars().all()
    
    # Mark all unread messages sent to the current user as read
    now = datetime.now(UTC).replace(tzinfo=None)
    for message in messages:
        if message.sender_id != current_user.id and not message.read_at:
            message.read_at = now
            message.status = "read"
    
    await db.commit()
    
    # Build responses
    return [
        MessageResponse(
            id=msg.id,
            conversation_id=msg.conversation_id,
            sender_id=msg.sender_id,
            content=msg.content,
            image_url=msg.media_url,
            is_read=bool(msg.read_at),
            created_at=msg.sent_at
        )
        for msg in messages
    ]


@router.patch("/messages/{message_id}/read", response_model=MessageResponse)
async def mark_message_read(
    message_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Mark a specific message as read.
    
    - Validates user is the recipient (not the sender)
    - Updates read_at timestamp
    """
    # Get message
    result = await db.execute(
        select(Message).where(Message.id == message_id)
    )
    message = result.scalar_one_or_none()
    
    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found"
        )
    
    # Get conversation to verify user is participant
    conv_result = await db.execute(
        select(Conversation).where(Conversation.id == message.conversation_id)
    )
    conversation = conv_result.scalar_one_or_none()
    
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )
    
    # Verify user is participant but not the sender
    participant_ids = [uuid.UUID(str(p)) for p in conversation.participants]
    if current_user.id not in participant_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a participant in this conversation"
        )
    
    if message.sender_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot mark own message as read"
        )
    
    # Mark as read
    if not message.read_at:
        message.read_at = datetime.now(UTC).replace(tzinfo=None)
        message.status = "read"
        await db.commit()
        await db.refresh(message)
    
    return MessageResponse(
        id=message.id,
        conversation_id=message.conversation_id,
        sender_id=message.sender_id,
        content=message.content,
        image_url=message.media_url,
        is_read=True,
        created_at=message.sent_at
    )
