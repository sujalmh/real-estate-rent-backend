"""Bookmark management API endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.orm import joinedload
from sqlalchemy.exc import IntegrityError

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.supporting import Bookmark
from app.models.listing import Listing
from app.models.user import User
from app.schemas.bookmark import (
    BookmarkCreate,
    BookmarkResponse,
    BookmarkListResponse,
)
from app.schemas.listing import ListingResponse

router = APIRouter(prefix="/api/v1/bookmarks", tags=["bookmarks"])


@router.post("", response_model=BookmarkResponse, status_code=status.HTTP_201_CREATED)
async def add_bookmark(
    bookmark_data: BookmarkCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BookmarkResponse:
    """
    Add a bookmark for a listing.

    - User must be authenticated
    - Cannot bookmark non-existent listings
    - Duplicate bookmarks return existing bookmark
    """
    # Check if listing exists
    listing_result = await db.execute(
        select(Listing)
        .options(joinedload(Listing.owner))
        .where(Listing.id == bookmark_data.listing_id)
    )
    listing = listing_result.scalar_one_or_none()
    
    if not listing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Listing not found",
        )

    # Create bookmark
    bookmark = Bookmark(
        user_id=current_user.id,
        listing_id=bookmark_data.listing_id,
    )

    try:
        db.add(bookmark)
        await db.commit()
        await db.refresh(bookmark)
    except IntegrityError:
        # Bookmark already exists, fetch and return it
        await db.rollback()
        result = await db.execute(
            select(Bookmark).where(
                and_(
                    Bookmark.user_id == current_user.id,
                    Bookmark.listing_id == bookmark_data.listing_id,
                )
            )
        )
        bookmark = result.scalar_one()

    # Build response with listing info
    response = BookmarkResponse.model_validate(bookmark)
    response.listing = ListingResponse.model_validate(listing)
    
    return response


@router.delete("/{listing_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_bookmark(
    listing_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Remove a bookmark.

    - User must be authenticated
    - Can only remove own bookmarks
    """
    result = await db.execute(
        select(Bookmark).where(
            and_(
                Bookmark.user_id == current_user.id,
                Bookmark.listing_id == listing_id,
            )
        )
    )
    bookmark = result.scalar_one_or_none()

    if not bookmark:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bookmark not found",
        )

    await db.delete(bookmark)
    await db.commit()


@router.get("", response_model=BookmarkListResponse)
async def list_bookmarks(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BookmarkListResponse:
    """
    List user's bookmarks with listing details.

    - Returns paginated list
    - Ordered by most recent first
    - Includes full listing information
    """
    # Base query
    query = select(Bookmark).where(Bookmark.user_id == current_user.id)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply pagination and ordering
    query = query.order_by(Bookmark.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    bookmarks = result.scalars().all()

    # Fetch listings for each bookmark
    bookmark_responses = []
    for bookmark in bookmarks:
        listing_result = await db.execute(
        select(Listing)
            .options(joinedload(Listing.owner))
            .where(Listing.id == bookmark.listing_id)
        )
        listing = listing_result.scalar_one_or_none()
        
        response = BookmarkResponse.model_validate(bookmark)
        if listing:
            response.listing = ListingResponse.model_validate(listing)
        bookmark_responses.append(response)

    return BookmarkListResponse(
        items=bookmark_responses,
        total=total,
        offset=offset,
        limit=limit,
    )
