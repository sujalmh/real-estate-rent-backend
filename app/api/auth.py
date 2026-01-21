from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.dependencies import get_current_user
from app.core.security import (
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    create_password_reset_token,
    decode_password_reset_token,
)
from app.database import get_db
from app.models.user import User
from app.schemas.auth import (
    Token,
    LoginRequest,
    RefreshTokenRequest,
    PasswordResetRequest,
    PasswordResetConfirm,
    ChangePasswordRequest,
)

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])


@router.post("/login", response_model=Token)
async def login(
    credentials: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Authenticate user with email and password.

    Returns JWT access and refresh tokens.
    """
    # Find user by email
    result = await db.execute(select(User).where(User.email == credentials.email))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    # Check if account is locked
    if user.locked_until and user.locked_until > datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Account is locked due to too many failed login attempts. Try again later.",
        )

    # Verify password
    if not verify_password(credentials.password, user.password_hash):
        # Increment failed login attempts
        user.failed_login_attempts += 1

        # Lock account after 5 failed attempts
        if user.failed_login_attempts >= 5:
            user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=15)
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account locked due to too many failed login attempts. Try again in 15 minutes.",
            )

        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    # Check if account is active
    if user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Account is {user.status}",
        )

    # Reset failed login attempts on successful login
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()

    # Create tokens
    access_token = create_access_token(user.id, user.email, user.roles)
    refresh_token = create_refresh_token(user.id)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


@router.post("/refresh", response_model=Token)
async def refresh_access_token(
    refresh_data: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Refresh access token using a valid refresh token.
    """
    payload = decode_token(refresh_data.refresh_token)

    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    # Get user from database
    from uuid import UUID

    result = await db.execute(select(User).where(User.id == UUID(user_id)))
    user = result.scalar_one_or_none()

    if not user or user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    # Create new tokens
    access_token = create_access_token(user.id, user.email, user.roles)
    refresh_token = create_refresh_token(user.id)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


@router.post("/logout")
async def logout(
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    Logout current user.

    Note: With JWT, actual logout is handled client-side by discarding tokens.
    This endpoint is mainly for consistency and could be extended with token blacklisting.
    """
    return {"message": "Successfully logged out"}


@router.post("/password-reset-request")
async def request_password_reset(
    reset_request: PasswordResetRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Request a password reset token.

    Sends a reset token via email (email sending to be implemented).
    """
    # Find user by email
    result = await db.execute(select(User).where(User.email == reset_request.email))
    user = result.scalar_one_or_none()

    # Always return success to prevent email enumeration
    if not user:
        return {
            "message": "If the email exists, a password reset link has been sent"
        }

    # Create reset token
    reset_token = create_password_reset_token(user.email)

    # TODO: Send email with reset token
    # For now, we'll just return it (in production, this should be sent via email)
    print(f"Password reset token for {user.email}: {reset_token}")

    return {
        "message": "If the email exists, a password reset link has been sent",
        # Remove this in production:
        "token": reset_token,
    }


@router.post("/password-reset-confirm")
async def confirm_password_reset(
    reset_confirm: PasswordResetConfirm,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Confirm password reset with token and new password.
    """
    # Decode and validate token
    email = decode_password_reset_token(reset_confirm.token)

    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        )

    # Find user
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Update password
    user.password_hash = hash_password(reset_confirm.new_password)
    user.failed_login_attempts = 0
    user.locked_until = None
    await db.commit()

    return {"message": "Password successfully reset"}


@router.post("/change-password")
async def change_password(
    password_change: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Change password for authenticated user.
    """
    # Verify current password
    if not verify_password(password_change.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect",
        )

    # Ensure new password is different
    if password_change.current_password == password_change.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be different from current password",
        )

    # Update password
    current_user.password_hash = hash_password(password_change.new_password)
    await db.commit()

    return {"message": "Password successfully changed"}
