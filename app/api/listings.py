"""Listing management API endpoints."""

import uuid
from datetime import datetime, timedelta, UTC
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import joinedload

from app.core.dependencies import get_current_user, get_optional_current_user
from app.database import get_db
from app.models.listing import Listing
from app.models.user import User
from app.schemas.listing import (
    ListingCreate,
    ListingUpdate,
    ListingResponse,
    ListingListResponse,
    ListingFilter,
    OwnerInfo,
)

router = APIRouter(prefix="/api/v1/listings", tags=["listings"])

# Constants
LISTING_EXPIRY_DAYS = 90
SUBSTANTIAL_CHANGE_FIELDS = {"title", "description", "price_amount"}


@router.post("", response_model=ListingResponse, status_code=status.HTTP_201_CREATED)
async def create_listing(
    listing_data: ListingCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Listing:
    """
    Create a new listing.

    - Sets initial status to 'pending_review'
    - Sets expiration date to 90 days from creation
    - Assigns unique ID and timestamps
    """
    # Check if user has owner or agent role
    if not any(role in current_user.roles for role in ["owner", "agent", "admin"]):
        # Automatically add owner role for creating listings
        current_user.roles = list(current_user.roles) + ["owner"]
    
    # Prepare images for JSONB storage
    images_data = None
    if listing_data.images:
        images_data = [img.model_dump() for img in listing_data.images]
    
    # Create listing
    new_listing = Listing(
        owner_id=current_user.id,
        type=listing_data.type.value,
        title=listing_data.title,
        description=listing_data.description,
        price_amount=float(listing_data.price_amount),
        price_currency=listing_data.price_currency,
        price_type=listing_data.price_type.value,
        address=listing_data.address,
        city=listing_data.city,
        state=listing_data.state,
        country=listing_data.country,
        postal_code=listing_data.postal_code,
        latitude=listing_data.latitude,
        longitude=listing_data.longitude,
        size=float(listing_data.size) if listing_data.size else None,
        amenities=listing_data.amenities,
        images=images_data,
        status="pending_review",
        moderation_status="pending",
        expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=LISTING_EXPIRY_DAYS),
    )

    db.add(new_listing)
    await db.commit()
    await db.refresh(new_listing)

    return new_listing


@router.get("/my-listings", response_model=ListingListResponse)
async def get_my_listings(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ListingListResponse:
    """
    Get current user's listings.
    """
    # Base query
    query = select(Listing).where(Listing.owner_id == current_user.id)

    # Filter by status
    # Owner can see all except deleted
    query = query.where(Listing.status != "deleted")
    if status_filter:
        query = query.where(Listing.status == status_filter)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply pagination and ordering
    query = query.order_by(Listing.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    listings = result.scalars().all()

    return ListingListResponse(
        items=[ListingResponse.model_validate(l) for l in listings],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/{listing_id}", response_model=ListingResponse)
async def get_listing(
    listing_id: uuid.UUID,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> ListingResponse:
    """
    Get a single listing by ID.

    - Increments view count (unless viewing own listing)
    - Includes owner information
    - Returns deleted listings only to owner
    """
    result = await db.execute(
        select(Listing).where(Listing.id == listing_id)
    )
    listing = result.scalar_one_or_none()

    if not listing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Listing not found",
        )

    # Check if listing is visible
    is_owner = current_user and current_user.id == listing.owner_id
    is_admin = current_user and "admin" in current_user.roles

    if listing.status == "deleted" and not (is_owner or is_admin):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Listing not found",
        )

    # Increment view count (unless viewing own listing)
    if not is_owner:
        listing.view_count += 1
        await db.commit()
        await db.refresh(listing)

    # Get owner info
    owner_result = await db.execute(
        select(User).where(User.id == listing.owner_id)
    )
    owner = owner_result.scalar_one_or_none()
    
    owner_info = None
    if owner:
        owner_info = OwnerInfo(
            id=owner.id,
            name=owner.name,
            verified=owner.verified,
            profile_photo=owner.profile_photo,
        )

    # Build response
    response = ListingResponse.model_validate(listing)
    response.owner = owner_info
    return response


@router.get("", response_model=ListingListResponse)
async def list_listings(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    type: Optional[str] = Query(default=None),
    city: Optional[str] = Query(default=None),
    price_min: Optional[float] = Query(default=None, ge=0),
    price_max: Optional[float] = Query(default=None, ge=0),
    db: AsyncSession = Depends(get_db),
) -> ListingListResponse:
    """
    List all active listings with pagination and filters.

    - Only returns active, non-deleted listings
    - Supports filtering by type, city, and price range
    """
    # Base query for active listings
    query = select(Listing).where(
        and_(
            Listing.status == "active",
            Listing.moderation_status == "approved",
        )
    )

    # Apply filters
    if type:
        query = query.where(Listing.type == type)
    if city:
        query = query.where(Listing.city.ilike(f"%{city}%"))
    if price_min is not None:
        query = query.where(Listing.price_amount >= price_min)
    if price_max is not None:
        query = query.where(Listing.price_amount <= price_max)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply pagination and ordering
    query = query.order_by(Listing.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    listings = result.scalars().all()

    # Convert listings to responses without triggering owner relationship
    items = []
    for listing in listings:
        # Create dict from listing attributes, excluding relationships
        listing_dict = {
            'id': listing.id,
            'owner_id': listing.owner_id,
            'type': listing.type,
            'title': listing.title,
            'description': listing.description,
            'price_amount': listing.price_amount,
            'price_currency': listing.price_currency,
            'price_type': listing.price_type,
            'address': listing.address,
            'city': listing.city,
            'state': listing.state,
            'country': listing.country,
            'postal_code': listing.postal_code,
            'latitude': listing.latitude,
            'longitude': listing.longitude,
            'size': listing.size,
            'amenities': listing.amenities,
            'images': listing.images,
            'status': listing.status,
            'moderation_status': listing.moderation_status,
            'rejection_reason': listing.rejection_reason,
            'view_count': listing.view_count,
            'lead_count': listing.lead_count,
            'promoted': listing.promoted,
            'promotion_expires_at': listing.promotion_expires_at,
            'expires_at': listing.expires_at,
            'created_at': listing.created_at,
            'updated_at': listing.updated_at,
        }
        items.append(ListingResponse(**listing_dict))

    return ListingListResponse(
        items=items,
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/user/{user_id}", response_model=ListingListResponse)
async def get_user_listings(
    user_id: uuid.UUID,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> ListingListResponse:
    """
    Get listings by owner.

    - If viewing own listings, shows all statuses
    - If viewing another user's listings, shows only active listings
    """
    is_owner = current_user and current_user.id == user_id
    is_admin = current_user and "admin" in current_user.roles

    # Base query
    query = select(Listing).where(Listing.owner_id == user_id)

    # Filter by status based on viewer permissions
    if is_owner or is_admin:
        # Owner/admin can see all except deleted
        query = query.where(Listing.status != "deleted")
        if status_filter:
            query = query.where(Listing.status == status_filter)
    else:
        # Others can only see active listings
        query = query.where(
            and_(
                Listing.status == "active",
                Listing.moderation_status == "approved",
            )
        )

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply pagination and ordering
    query = query.order_by(Listing.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    listings = result.scalars().all()

    return ListingListResponse(
        items=[ListingResponse.model_validate(l) for l in listings],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.put("/{listing_id}", response_model=ListingResponse)
async def update_listing(
    listing_id: uuid.UUID,
    update_data: ListingUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Listing:
    """
    Update a listing.

    - Only the owner can update their listing
    - Substantial changes (title, description, price) reset to pending_review
    """
    result = await db.execute(
        select(Listing).where(Listing.id == listing_id)
    )
    listing = result.scalar_one_or_none()

    if not listing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Listing not found",
        )

    # Check ownership
    if listing.owner_id != current_user.id and "admin" not in current_user.roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only update your own listings",
        )

    # Check if listing can be updated
    if listing.status == "deleted":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot update a deleted listing",
        )

    # Get update dict
    update_dict = update_data.model_dump(exclude_unset=True)

    # Check for substantial changes
    has_substantial_change = bool(set(update_dict.keys()) & SUBSTANTIAL_CHANGE_FIELDS)

    # Handle special fields
    if "images" in update_dict and update_dict["images"]:
        update_dict["images"] = [img.model_dump() if hasattr(img, 'model_dump') else img for img in update_dict["images"]]
    
    if "price_type" in update_dict and update_dict["price_type"]:
        update_dict["price_type"] = update_dict["price_type"].value if hasattr(update_dict["price_type"], 'value') else update_dict["price_type"]

    # Update fields
    for key, value in update_dict.items():
        setattr(listing, key, value)

    # Reset to pending review if substantial changes
    if has_substantial_change and listing.moderation_status == "approved":
        listing.status = "pending_review"
        listing.moderation_status = "pending"

    await db.commit()
    await db.refresh(listing)

    return listing


@router.patch("/{listing_id}/pause", response_model=ListingResponse)
async def pause_listing(
    listing_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Listing:
    """
    Pause a listing.

    - Hides listing from search results
    - Preserves all listing data
    """
    result = await db.execute(
        select(Listing).where(Listing.id == listing_id)
    )
    listing = result.scalar_one_or_none()

    if not listing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Listing not found",
        )

    # Check ownership
    if listing.owner_id != current_user.id and "admin" not in current_user.roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only pause your own listings",
        )

    # Check if listing can be paused
    if listing.status not in ["active", "pending_review"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot pause listing with status '{listing.status}'",
        )

    listing.status = "paused"
    await db.commit()
    await db.refresh(listing)

    return listing


@router.patch("/{listing_id}/reactivate", response_model=ListingResponse)
async def reactivate_listing(
    listing_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Listing:
    """
    Reactivate a paused listing.

    - Restores listing to search results
    - Only works on paused listings
    """
    result = await db.execute(
        select(Listing).where(Listing.id == listing_id)
    )
    listing = result.scalar_one_or_none()

    if not listing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Listing not found",
        )

    # Check ownership
    if listing.owner_id != current_user.id and "admin" not in current_user.roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only reactivate your own listings",
        )

    # Check if listing can be reactivated
    if listing.status != "paused":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot reactivate listing with status '{listing.status}'. Only paused listings can be reactivated.",
        )

    # Check moderation status
    if listing.moderation_status == "approved":
        listing.status = "active"
    else:
        listing.status = "pending_review"

    # Reset expiration
    listing.expires_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(days=LISTING_EXPIRY_DAYS)

    await db.commit()
    await db.refresh(listing)

    return listing


@router.delete("/{listing_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_listing(
    listing_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Soft delete a listing.

    - Marks listing as deleted (not removed from database)
    - Hides from all search results
    """
    result = await db.execute(
        select(Listing).where(Listing.id == listing_id)
    )
    listing = result.scalar_one_or_none()

    if not listing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Listing not found",
        )

    # Check ownership
    if listing.owner_id != current_user.id and "admin" not in current_user.roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only delete your own listings",
        )

    # Check if already deleted
    if listing.status == "deleted":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Listing is already deleted",
        )

    listing.status = "deleted"
    await db.commit()


@router.post("/{listing_id}/view", status_code=status.HTTP_204_NO_CONTENT)
async def track_view(
    listing_id: uuid.UUID,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Track a view for a listing.

    - Increments listing view count
    - Adds to user's view history (if authenticated)
    - Does not track if viewing own listing
    """
    from app.models.supporting import ViewHistory
    
    result = await db.execute(
        select(Listing).where(Listing.id == listing_id)
    )
    listing = result.scalar_one_or_none()

    if not listing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Listing not found",
        )

    # Check if user is the owner
    is_owner = current_user and current_user.id == listing.owner_id

    if not is_owner:
        # Increment view count
        listing.view_count += 1
        
        # Add to view history if user is authenticated
        if current_user:
            # Create view history record
            view_record = ViewHistory(
                user_id=current_user.id,
                listing_id=listing_id,
            )
            db.add(view_record)
        
        await db.commit()


@router.get("/view-history/recent", response_model=ListingListResponse)
async def get_view_history(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ListingListResponse:
    """
    Get user's recent view history.

    - Returns up to 50 most recently viewed listings
    - Ordered by most recent first
    - Includes full listing information
    """
    from app.models.supporting import ViewHistory
    
    # Get view history records
    query = select(ViewHistory).where(ViewHistory.user_id == current_user.id)
    
    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0
    
    # Apply pagination and ordering
    query = query.order_by(ViewHistory.viewed_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    view_records = result.scalars().all()

    # Fetch listings for each view record
    listing_responses = []
    seen_listing_ids = set()
    
    for record in view_records:
        # Skip duplicate listings (show only most recent view)
        if record.listing_id in seen_listing_ids:
            continue
        seen_listing_ids.add(record.listing_id)
        
        listing_result = await db.execute(
            select(Listing).options(joinedload(Listing.owner)).where(Listing.id == record.listing_id)
        )
        listing = listing_result.scalar_one_or_none()
        
        if listing:
            listing_responses.append(ListingResponse.model_validate(listing))

    return ListingListResponse(
        items=listing_responses,
        total=total,
        offset=offset,
        limit=limit,
    )

