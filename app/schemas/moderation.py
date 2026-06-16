"""Moderation schemas for admin operations."""

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


class ModerationQueueItem(BaseModel):
    """Schema for listing in moderation queue."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    title: str
    type: str
    owner_id: UUID
    owner_name: str
    price_amount: Decimal
    city: Optional[str]
    created_at: datetime
    moderation_status: str


class ListingRejection(BaseModel):
    """Schema for rejecting a listing."""
    reason: str = Field(..., min_length=10, max_length=500, description="Reason for rejection")
