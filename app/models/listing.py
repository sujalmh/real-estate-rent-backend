"""Listing model definition."""

import uuid
from datetime import datetime
from typing import Optional, List

from sqlalchemy import String, Boolean, Integer, Float, Text, ARRAY, TIMESTAMP, DECIMAL, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Listing(Base):
    """Listing table model."""

    __tablename__ = "listings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    
    # Type: land, rental, pg
    type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Price
    price_amount: Mapped[float] = mapped_column(DECIMAL(15, 2), nullable=False)
    price_currency: Mapped[str] = mapped_column(String(3), default="INR")
    price_type: Mapped[str] = mapped_column(String(20), default="sale")  # sale, monthly, daily
    
    # Location
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    state: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    country: Mapped[str] = mapped_column(String(100), default="India")
    postal_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Property details
    size: Mapped[Optional[float]] = mapped_column(DECIMAL(10, 2), nullable=True)  # sq ft
    amenities: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String), nullable=True)
    images: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)  # [{url, is_primary, order}]
    
    # Status
    status: Mapped[str] = mapped_column(
        String(20), default="pending_review", index=True
    )  # draft, pending_review, active, paused, expired, deleted
    moderation_status: Mapped[str] = mapped_column(
        String(20), default="pending"
    )  # pending, approved, rejected, flagged
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Metrics
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    lead_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # Promotion
    promoted: Mapped[bool] = mapped_column(Boolean, default=False)
    promotion_expires_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP, nullable=True)
    
    # Timestamps
    expires_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, default=datetime.utcnow, nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Relationships
    owner = relationship("User", back_populates="listings")
    conversations = relationship("Conversation", back_populates="listing", lazy="dynamic")

    def __repr__(self) -> str:
        return f"<Listing {self.title}>"
