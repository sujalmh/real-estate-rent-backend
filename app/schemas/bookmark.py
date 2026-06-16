"""Bookmark Pydantic schemas for request/response validation."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

# Import ListingResponse to include in bookmark response
from app.schemas.listing import ListingResponse


class BookmarkCreate(BaseModel):
    """Schema for creating a bookmark."""
    listing_id: uuid.UUID


class BookmarkResponse(BaseModel):
    """Schema for bookmark response."""
    user_id: uuid.UUID
    listing_id: uuid.UUID
    created_at: datetime
    listing: Optional[ListingResponse] = None

    model_config = ConfigDict(from_attributes=True)


class BookmarkListResponse(BaseModel):
    """Schema for paginated bookmark list response."""
    items: list[BookmarkResponse]
    total: int
    offset: int
    limit: int
