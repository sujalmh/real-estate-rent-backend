"""User Pydantic schemas for request/response validation."""

import re
import uuid
from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, EmailStr, Field, field_validator


class UserBase(BaseModel):
    """Base user schema with common fields."""

    email: EmailStr
    phone: Optional[str] = Field(None, pattern=r"^\+?[1-9]\d{9,14}$")
    name: str = Field(..., min_length=1, max_length=255)


class UserCreate(UserBase):
    """Schema for user registration."""

    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """Validate password meets strength requirements."""
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", v):
            raise ValueError("Password must contain at least one special character")
        return v


class UserUpdate(BaseModel):
    """Schema for updating user profile."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    phone: Optional[str] = Field(None, pattern=r"^\+?[1-9]\d{9,14}$")
    profile_photo: Optional[str] = None
    bio: Optional[str] = Field(None, max_length=1000)
    privacy_settings: Optional[dict] = None


class UserResponse(BaseModel):
    """Schema for user response (public data)."""

    id: uuid.UUID
    email: EmailStr
    phone: Optional[str] = None
    name: str
    profile_photo: Optional[str] = None
    bio: Optional[str] = None
    roles: List[str]
    verified: bool
    status: str
    created_at: datetime
    updated_at: datetime
    privacy_settings: Optional[dict] = None

    model_config = {"from_attributes": True}


class UserProfileResponse(BaseModel):
    """Schema for user profile response (may hide contact info based on privacy)."""

    id: uuid.UUID
    name: str
    profile_photo: Optional[str] = None
    bio: Optional[str] = None
    roles: List[str]
    verified: bool
    # Contact info may be hidden based on privacy settings
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PrivacySettings(BaseModel):
    """Schema for privacy settings."""

    hide_email: bool = False
    hide_phone: bool = False
    show_online_status: bool = True
