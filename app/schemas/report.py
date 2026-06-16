"""Report schemas for content reporting."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, ConfigDict


class ReportCreate(BaseModel):
    """Schema for creating a report."""
    listing_id: UUID
    category: str = Field(..., description="Report category")
    details: str = Field(..., min_length=10, max_length=1000, description="Report details")
    
    @field_validator('category')
    @classmethod
    def validate_category(cls, v: str) -> str:
        """Validate report category."""
        valid_categories = ["spam", "fraud", "inappropriate", "duplicate", "incorrect_info"]
        if v not in valid_categories:
            raise ValueError(f"Category must be one of: {', '.join(valid_categories)}")
        return v


class ReportResponse(BaseModel):
    """Schema for report response."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    reporter_id: UUID
    listing_id: UUID
    category: str
    details: str
    status: str
    reviewed_by: Optional[UUID]
    reviewed_at: Optional[datetime]
    action: Optional[str]
    created_at: datetime
    # Additional context
    listing_title: Optional[str] = None
    reporter_name: Optional[str] = None
