"""Listing Pydantic schemas for request/response validation."""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional, List

from pydantic import BaseModel, Field, field_validator, HttpUrl, ConfigDict


class ListingType(str, Enum):
    """Types of listings."""
    LAND = "land"
    RENTAL = "rental"
    PG = "pg"


class ListingStatus(str, Enum):
    """Listing status values."""
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    ACTIVE = "active"
    PAUSED = "paused"
    EXPIRED = "expired"
    DELETED = "deleted"


class ModerationStatus(str, Enum):
    """Moderation status values."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    FLAGGED = "flagged"


class PriceType(str, Enum):
    """Price type values."""
    SALE = "sale"
    MONTHLY = "monthly"
    DAILY = "daily"


class ImageInfo(BaseModel):
    """Schema for image metadata."""
    url: str = Field(..., description="URL of the image")
    is_primary: bool = Field(default=False, description="Whether this is the primary image")
    order: int = Field(default=0, ge=0, description="Display order of the image")

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Validate image URL format."""
        if not v.startswith(("http://", "https://")):
            raise ValueError("Image URL must start with http:// or https://")
        return v


class ListingBase(BaseModel):
    """Base listing schema with common fields."""
    type: ListingType
    title: str = Field(..., min_length=3, max_length=255)
    description: Optional[str] = Field(None, max_length=5000)
    
    # Price
    price_amount: Decimal = Field(..., gt=0, decimal_places=2)
    price_currency: str = Field(default="INR", pattern=r"^[A-Z]{3}$")
    price_type: PriceType = Field(default=PriceType.MONTHLY)
    
    # Location
    address: Optional[str] = Field(None, max_length=500)
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    country: str = Field(default="India", max_length=100)
    postal_code: Optional[str] = Field(None, pattern=r"^\d{6}$")
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    
    # Property details
    size: Optional[Decimal] = Field(None, gt=0, description="Size in sq ft")
    amenities: Optional[List[str]] = Field(default=None)
    images: Optional[List[ImageInfo]] = Field(default=None)


class ListingCreate(ListingBase):
    """Schema for creating a listing."""
    pass


class ListingUpdate(BaseModel):
    """Schema for updating a listing."""
    title: Optional[str] = Field(None, min_length=3, max_length=255)
    description: Optional[str] = Field(None, max_length=5000)
    
    # Price
    price_amount: Optional[Decimal] = Field(None, gt=0, decimal_places=2)
    price_currency: Optional[str] = Field(None, pattern=r"^[A-Z]{3}$")
    price_type: Optional[PriceType] = None
    
    # Location
    address: Optional[str] = Field(None, max_length=500)
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    country: Optional[str] = Field(None, max_length=100)
    postal_code: Optional[str] = Field(None, pattern=r"^\d{6}$")
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    
    # Property details
    size: Optional[Decimal] = Field(None, gt=0)
    amenities: Optional[List[str]] = None
    images: Optional[List[ImageInfo]] = None


class OwnerInfo(BaseModel):
    """Schema for owner information in listing response."""
    id: uuid.UUID
    name: str
    verified: bool
    profile_photo: Optional[str] = None

    model_config = {"from_attributes": True}


class ListingResponse(BaseModel):
    """Schema for listing response."""
    id: uuid.UUID
    owner_id: uuid.UUID
    type: str
    title: str
    description: Optional[str] = None
    
    # Price
    price_amount: Decimal
    price_currency: str
    price_type: str
    
    # Location
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: str
    postal_code: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    
    # Property details
    size: Optional[Decimal] = None
    amenities: Optional[List[str]] = None
    images: Optional[List[dict]] = None
    
    # Status
    status: str
    moderation_status: str
    rejection_reason: Optional[str] = None
    
    # Metrics
    view_count: int
    lead_count: int
    
    # Promotion
    promoted: bool
    promotion_expires_at: Optional[datetime] = None
    
    # Timestamps
    expires_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    
    # Owner info (optional, populated when needed)
    owner: Optional[OwnerInfo] = None
    
    # Distance from user (optional, for search results)
    distance: Optional[float] = None
    
    # Combined relevance score (optional, for search results)
    score: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)


class ListingListResponse(BaseModel):
    """Schema for paginated listing list response."""
    items: List[ListingResponse]
    total: int
    offset: int
    limit: int
    is_fallback_result: bool = False  # True when showing nearby listings as fallback


class ListingFilter(BaseModel):
    """Schema for filtering listings."""
    type: Optional[ListingType] = None
    name: Optional[str] = None  # Search by property title/name
    city: Optional[str] = None
    state: Optional[str] = None
    price_min: Optional[Decimal] = Field(None, ge=0)
    price_max: Optional[Decimal] = Field(None, ge=0)
    status: Optional[ListingStatus] = None
    amenities: Optional[List[str]] = None


class SortOption(str, Enum):
    """Sort options for listings."""
    PRICE_ASC = "price_asc"
    PRICE_DESC = "price_desc"
    DATE_DESC = "date_desc"
    DATE_ASC = "date_asc"
    DISTANCE = "distance"  # Nearest first (requires user location)
    SCORE = "score"  # Combined score: distance + popularity + freshness


class SearchRequest(BaseModel):
    """Schema for search request."""
    filters: Optional[ListingFilter] = None
    sort: Optional[SortOption] = Field(default=SortOption.SCORE)
    user_latitude: Optional[float] = Field(None, ge=-90, le=90)
    user_longitude: Optional[float] = Field(None, ge=-180, le=180)
    radius_km: Optional[float] = Field(None, gt=0, le=500, description="Search radius in kilometers")
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)
