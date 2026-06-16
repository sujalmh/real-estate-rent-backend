"""Search API endpoints with PostGIS geography support."""

import math
from typing import Optional
from datetime import datetime, UTC

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, case, cast, Float
from sqlalchemy.orm import joinedload
from geoalchemy2 import Geography
from geoalchemy2.functions import ST_DWithin, ST_Distance, ST_MakePoint

from app.database import get_db
from app.models.listing import Listing
from app.models.user import User
from app.schemas.listing import (
    SearchRequest,
    ListingListResponse,
    ListingResponse,
    SortOption,
)

router = APIRouter(prefix="/api/v1/search", tags=["search"])

# Constants for scoring algorithm
MAX_DISTANCE_KM = 50.0  # For normalization
MAX_LOG_VIEWS = 3.0  # log10(1000) ≈ 3
MAX_AGE_DAYS = 90.0  # Normalize freshness
DISTANCE_WEIGHT = 0.5
POPULARITY_WEIGHT = 0.3
FRESHNESS_WEIGHT = 0.2
DEFAULT_RADIUS_KM = 25.0  # Default search radius


@router.post("/listings", response_model=ListingListResponse)
async def search_listings(
    search_req: SearchRequest,
    db: AsyncSession = Depends(get_db),
) -> ListingListResponse:
    """
    Search listings with PostGIS geography-based filtering and scoring.
    
    Features:
    - Radius-based search using ST_DWithin
    - Precise distance calculation using ST_Distance
    - Combined scoring: distance + popularity (views) + freshness (created_at)
    - Fallback to nearby listings when no exact matches found
    """
    
    # Base query for active, approved listings
    base_conditions = [
        Listing.status == "active",
        Listing.moderation_status == "approved",
    ]
    
    # Build main query
    query = select(Listing).options(joinedload(Listing.owner))
    
    # Apply filters
    if search_req.filters:
        filters = search_req.filters
        
        if filters.type:
            base_conditions.append(Listing.type == filters.type.value)
        
        if filters.name:
            base_conditions.append(Listing.title.ilike(f"%{filters.name}%"))
        
        if filters.city:
            base_conditions.append(Listing.city.ilike(f"%{filters.city}%"))
        
        if filters.state:
            base_conditions.append(Listing.state.ilike(f"%{filters.state}%"))
        
        if filters.price_min is not None:
            base_conditions.append(Listing.price_amount >= float(filters.price_min))
        
        if filters.price_max is not None:
            base_conditions.append(Listing.price_amount <= float(filters.price_max))
        
        if filters.amenities:
            for amenity in filters.amenities:
                base_conditions.append(Listing.amenities.contains([amenity]))
    
    # Apply radius-based filtering if user location provided
    user_point = None
    distance_expr = None
    
    if search_req.user_latitude is not None and search_req.user_longitude is not None:
        # Create point from user coordinates
        user_point = func.ST_SetSRID(
            ST_MakePoint(search_req.user_longitude, search_req.user_latitude),
            4326
        )
        
        # Require listings to have location data
        base_conditions.append(Listing.location.isnot(None))
        
        # Apply radius filter if specified
        if search_req.radius_km:
            radius_meters = search_req.radius_km * 1000
            base_conditions.append(
                ST_DWithin(
                    cast(Listing.location, Geography),
                    cast(user_point, Geography),
                    radius_meters
                )
            )
        
        # Calculate distance in kilometers
        distance_expr = (
            ST_Distance(
                cast(Listing.location, Geography),
                cast(user_point, Geography)
            ) / 1000.0
        ).label('distance_km')
    
    # Calculate scoring components if we have user location
    score_expr = None
    if user_point is not None and distance_expr is not None:
        # Distance score: closer = higher (0 to 1)
        distance_score = case(
            (distance_expr <= MAX_DISTANCE_KM, 1.0 - (distance_expr / MAX_DISTANCE_KM)),
            else_=0.0
        )
        
        # Popularity score: more views = higher (0 to 1, log scale)
        popularity_score = func.least(
            1.0,
            func.log(10, Listing.view_count + 1) / MAX_LOG_VIEWS
        )
        
        # Freshness score: newer = higher (0 to 1)
        days_since_creation = func.extract(
            'epoch',
            func.now() - Listing.created_at
        ) / 86400.0  # Convert seconds to days
        
        freshness_score = func.greatest(
            0.0,
            1.0 - (days_since_creation / MAX_AGE_DAYS)
        )
        
        # Combined weighted score
        score_expr = (
            (DISTANCE_WEIGHT * distance_score) +
            (POPULARITY_WEIGHT * popularity_score) +
            (FRESHNESS_WEIGHT * freshness_score)
        ).label('score')
    
    # Build query with all conditions
    query = query.where(and_(*base_conditions))
    
    # Add distance and score to SELECT if available
    if distance_expr is not None:
        query = query.add_columns(distance_expr)
    if score_expr is not None:
        query = query.add_columns(score_expr)
    
    # Apply sorting
    if search_req.sort == SortOption.DISTANCE and distance_expr is not None:
        query = query.order_by(distance_expr.asc())
    elif search_req.sort == SortOption.SCORE and score_expr is not None:
        query = query.order_by(score_expr.desc())
    elif search_req.sort == SortOption.PRICE_ASC:
        query = query.order_by(Listing.price_amount.asc())
    elif search_req.sort == SortOption.PRICE_DESC:
        query = query.order_by(Listing.price_amount.desc())
    elif search_req.sort == SortOption.DATE_ASC:
        query = query.order_by(Listing.created_at.asc())
    elif search_req.sort == SortOption.DATE_DESC:
        query = query.order_by(Listing.created_at.desc())
    else:  # SCORE or default
        # Use score if available, otherwise fall back to date desc
        if score_expr is not None:
            query = query.order_by(score_expr.desc())
        else:
            query = query.order_by(Listing.created_at.desc())
    
    # Get total count for primary search
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0
    
    # Track if this is a fallback result
    is_fallback = False
    
    # Fallback: If no results and user location provided, find nearest listings
    if total == 0 and user_point is not None:
        is_fallback = True
        
        # Build fallback query: remove city/name filters, keep type filter
        fallback_conditions = [
            Listing.status == "active",
            Listing.moderation_status == "approved",
            Listing.location.isnot(None),
        ]
        
        # Keep type filter if present
        if search_req.filters and search_req.filters.type:
            fallback_conditions.append(Listing.type == search_req.filters.type.value)
        
        # Recalculate distance for fallback
        fallback_distance_expr = (
            ST_Distance(
                cast(Listing.location, Geography),
                cast(user_point, Geography)
            ) / 1000.0
        ).label('distance_km')
        
        fallback_query = select(Listing).options(joinedload(Listing.owner))
        fallback_query = fallback_query.where(and_(*fallback_conditions))
        fallback_query = fallback_query.add_columns(fallback_distance_expr)
        
        # Apply sorting to fallback results
        if search_req.sort == SortOption.PRICE_ASC:
            fallback_query = fallback_query.order_by(Listing.price_amount.asc())
        elif search_req.sort == SortOption.PRICE_DESC:
            fallback_query = fallback_query.order_by(Listing.price_amount.desc())
        elif search_req.sort == SortOption.DATE_ASC:
            fallback_query = fallback_query.order_by(Listing.created_at.asc())
        elif search_req.sort == SortOption.DATE_DESC:
            fallback_query = fallback_query.order_by(Listing.created_at.desc())
        else:
            # Default to distance for SCORE or DISTANCE sort (since we don't calculate score for fallback)
            fallback_query = fallback_query.order_by(fallback_distance_expr.asc())
        
        # Get count
        fallback_count_query = select(func.count()).select_from(fallback_query.subquery())
        total_result = await db.execute(fallback_count_query)
        total = total_result.scalar() or 0
        
        # Use fallback query for results
        query = fallback_query
        distance_expr = fallback_distance_expr
        # Don't calculate score for fallback results
        score_expr = None
    
    # Apply pagination
    query = query.offset(search_req.offset).limit(search_req.limit)
    result = await db.execute(query)
    
    # Process results
    listing_responses = []
    
    if distance_expr is not None or score_expr is not None:
        # Results have extra columns (distance and/or score)
        for row in result.all():
            listing = row[0]  # First column is the Listing object
            resp = ListingResponse.model_validate(listing)
            
            # Add distance if available
            if distance_expr is not None and len(row) > 1:
                resp.distance = round(float(row[1]), 1)
            
            # Add score if available (and not fallback)
            if score_expr is not None and len(row) > 2 and not is_fallback:
                resp.score = round(float(row[2]), 3)
            
            listing_responses.append(resp)
    else:
        # Standard results without distance/score
        listings = result.scalars().all()
        listing_responses = [ListingResponse.model_validate(l) for l in listings]
    
    return ListingListResponse(
        items=listing_responses,
        total=total,
        offset=search_req.offset,
        limit=search_req.limit,
        is_fallback_result=is_fallback,
    )
