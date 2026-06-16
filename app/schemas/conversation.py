"""Conversation schemas for messaging system."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


class ConversationCreate(BaseModel):
    """Schema for creating a new conversation."""
    listing_id: UUID = Field(..., description="ID of the listing being discussed")
    recipient_id: UUID = Field(..., description="ID of the user to start conversation with")


class ConversationResponse(BaseModel):
    """Schema for conversation response."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    listing_id: UUID
    initiator_id: UUID
    recipient_id: UUID
    listing_title: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    last_message_preview: Optional[str] = None
    unread_count: int = 0
