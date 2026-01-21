"""Authentication Pydantic schemas."""

import uuid
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class Token(BaseModel):
    """JWT token response schema."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    """Data extracted from JWT token."""

    user_id: uuid.UUID
    email: str
    roles: list[str]
    exp: int


class LoginRequest(BaseModel):
    """Schema for email/password login."""

    email: EmailStr
    password: str


class PhoneLoginRequest(BaseModel):
    """Schema for phone/OTP login."""

    phone: str = Field(..., pattern=r"^\+?[1-9]\d{9,14}$")
    otp: str = Field(..., min_length=6, max_length=6)


class OTPRequest(BaseModel):
    """Schema for requesting OTP."""

    phone: str = Field(..., pattern=r"^\+?[1-9]\d{9,14}$")


class RefreshTokenRequest(BaseModel):
    """Schema for refreshing access token."""

    refresh_token: str


class PasswordResetRequest(BaseModel):
    """Schema for requesting password reset."""

    email: EmailStr


class PasswordResetConfirm(BaseModel):
    """Schema for confirming password reset."""

    token: str
    new_password: str = Field(..., min_length=8, max_length=128)


class ChangePasswordRequest(BaseModel):
    """Schema for changing password."""

    current_password: str
    new_password: str = Field(..., min_length=8, max_length=128)
