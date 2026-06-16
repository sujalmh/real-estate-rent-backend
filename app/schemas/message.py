"""Message schemas for messaging system."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, ConfigDict


class MessageCreate(BaseModel):
    """Schema for creating a new message."""
    content: str = Field(..., min_length=1, max_length=2000, description="Message content")
    image_url: Optional[str] = Field(None, description="Optional image URL")

    @field_validator('content')
    @classmethod
    def validate_content(cls, v: str) -> str:
        """Validate message content is not empty or just whitespace."""
        if not v or not v.strip():
            raise ValueError("Message content cannot be empty")
        return v.strip()


class MessageResponse(BaseModel):
    """Schema for message response."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    conversation_id: UUID
    sender_id: UUID
    content: str
    image_url: Optional[str] = None
    is_read: bool = False
    created_at: datetime
