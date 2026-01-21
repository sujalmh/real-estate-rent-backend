"""User management API endpoints."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.dependencies import get_current_user, get_optional_current_user
from app.core.security import hash_password
from app.database import get_db
from app.models.user import User
from app.schemas.user import (
    UserCreate,
    UserUpdate,
    UserResponse,
    UserProfileResponse,
    PrivacySettings,
)

router = APIRouter(prefix="/api/v1/users", tags=["users"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register_user(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Register a new user.

    - Validates email uniqueness
    - Validates phone uniqueness (if provided)
    - Hashes password using bcrypt
    - Creates user with 'seeker' role by default
    """
    # Check if email already exists
    result = await db.execute(select(User).where(User.email == user_data.email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Check if phone already exists (if provided)
    if user_data.phone:
        result = await db.execute(select(User).where(User.phone == user_data.phone))
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Phone number already registered",
            )

    # Hash password
    password_hash = hash_password(user_data.password)

    # Create user
    new_user = User(
        email=user_data.email,
        phone=user_data.phone,
        password_hash=password_hash,
        name=user_data.name,
        roles=["seeker"],  # Default role
        verified=False,
        status="active",
    )

    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    return new_user


@router.get("/{user_id}/profile", response_model=UserProfileResponse)
async def get_user_profile(
    user_id: uuid.UUID,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserProfileResponse:
    """
    Get user profile by ID.

    - Contact information may be hidden based on privacy settings
    - If viewing own profile, all information is visible
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Build response based on privacy settings
    response_data = {
        "id": user.id,
        "name": user.name,
        "profile_photo": user.profile_photo,
        "bio": user.bio,
        "roles": user.roles,
        "verified": user.verified,
        "created_at": user.created_at,
    }

    # If viewing own profile or user has no privacy settings, show all info
    is_own_profile = current_user and current_user.id == user.id
    privacy = user.privacy_settings or {}

    if is_own_profile or not privacy.get("hide_email", False):
        response_data["email"] = user.email

    if is_own_profile or not privacy.get("hide_phone", False):
        response_data["phone"] = user.phone

    return UserProfileResponse(**response_data)


@router.put("/{user_id}/profile", response_model=UserResponse)
async def update_user_profile(
    user_id: uuid.UUID,
    update_data: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Update user profile.

    - Users can only update their own profile
    - Phone number uniqueness is validated if changed
    """
    # Check if user is updating their own profile
    if current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only update your own profile",
        )

    # Validate phone uniqueness if provided
    if update_data.phone:
        result = await db.execute(
            select(User).where(User.phone == update_data.phone, User.id != user_id)
        )
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Phone number already in use",
            )

    # Update user fields
    update_dict = update_data.model_dump(exclude_unset=True)
    for key, value in update_dict.items():
        setattr(current_user, key, value)

    await db.commit()
    await db.refresh(current_user)

    return current_user


@router.patch("/{user_id}/profile", response_model=UserResponse)
async def partial_update_profile(
    user_id: uuid.UUID,
    update_data: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Partially update user profile (same as PUT for this implementation).
    """
    return await update_user_profile(user_id, update_data, current_user, db)


@router.post("/{user_id}/roles")
async def add_user_role(
    user_id: uuid.UUID,
    role: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Add a role to a user.

    - Only admins can add roles
    - Valid roles: seeker, owner, agent, admin
    """
    # Check if current user is admin
    if "admin" not in current_user.roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can add roles",
        )

    # Get target user
    result = await db.execute(select(User).where(User.id == user_id))
    target_user = result.scalar_one_or_none()

    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Validate role
    valid_roles = ["seeker", "owner", "agent", "admin"]
    if role not in valid_roles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role. Valid roles: {valid_roles}",
        )

    # Add role if not already present
    if role not in target_user.roles:
        target_user.roles.append(role)
        await db.commit()

    return {"message": f"Role '{role}' added to user", "roles": target_user.roles}


@router.delete("/{user_id}/roles/{role}")
async def remove_user_role(
    user_id: uuid.UUID,
    role: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Remove a role from a user.

    - Only admins can remove roles
    """
    # Check if current user is admin
    if "admin" not in current_user.roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can remove roles",
        )

    # Get target user
    result = await db.execute(select(User).where(User.id == user_id))
    target_user = result.scalar_one_or_none()

    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Remove role if present
    if role in target_user.roles:
        target_user.roles.remove(role)
        await db.commit()
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User does not have role '{role}'",
        )

    return {"message": f"Role '{role}' removed from user", "roles": target_user.roles}
