"""Report API endpoints for content reporting."""

import uuid
from typing import List, Optional
from datetime import datetime, UTC

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.core.dependencies import get_current_user, get_current_admin
from app.database import get_db
from app.models.user import User
from app.models.listing import Listing
from app.models.supporting import Report
from app.schemas.report import ReportCreate, ReportResponse

router = APIRouter(prefix="/api/v1", tags=["reports"])


@router.post("/reports", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
async def create_report(
    report_data: ReportCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a report for a listing.
    
    - Authenticated users only
    - Validates listing exists
    - Prevents duplicate reports (same user + listing)
    """
    # Verify listing exists
    result = await db.execute(
        select(Listing).where(Listing.id == report_data.listing_id)
    )
    listing = result.scalar_one_or_none()
    
    if not listing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Listing not found"
        )
    
    # Check for duplicate report
    existing_result = await db.execute(
        select(Report).where(
            and_(
                Report.reporter_id == current_user.id,
                Report.listing_id == report_data.listing_id
            )
        )
    )
    existing_report = existing_result.scalar_one_or_none()
    
    if existing_report:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You have already reported this listing"
        )
    
    # Create report
    new_report = Report(
        reporter_id=current_user.id,
        listing_id=report_data.listing_id,
        category=report_data.category,
        details=report_data.details,
        status="pending"
    )
    db.add(new_report)
    await db.commit()
    await db.refresh(new_report)
    
    return ReportResponse(
        id=new_report.id,
        reporter_id=new_report.reporter_id,
        listing_id=new_report.listing_id,
        category=new_report.category,
        details=new_report.details,
        status=new_report.status,
        reviewed_by=new_report.reviewed_by,
        reviewed_at=new_report.reviewed_at,
        action=new_report.action,
        created_at=new_report.created_at,
        listing_title=listing.title,
        reporter_name=current_user.name
    )


@router.get("/admin/reports", response_model=List[ReportResponse])
async def list_reports(
    status_filter: Optional[str] = Query(default=None, alias="status"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    List all reports (admin only).
    
    - Requires admin role
    - Optional filtering by status
    - Includes listing title and reporter name
    - Ordered by creation date (newest first)
    """
    # Build query
    query = select(Report)
    
    # Apply status filter if provided
    if status_filter:
        query = query.where(Report.status == status_filter)
    
    # Apply pagination and ordering
    query = query.order_by(Report.created_at.desc()).offset(offset).limit(limit)
    
    result = await db.execute(query)
    reports = result.scalars().all()
    
    # Build responses with additional context
    responses = []
    for report in reports:
        # Get listing info
        listing_title = None
        listing_result = await db.execute(
            select(Listing).where(Listing.id == report.listing_id)
        )
        listing = listing_result.scalar_one_or_none()
        if listing:
            listing_title = listing.title
        
        # Get reporter info
        reporter_name = None
        reporter_result = await db.execute(
            select(User).where(User.id == report.reporter_id)
        )
        reporter = reporter_result.scalar_one_or_none()
        if reporter:
            reporter_name = reporter.name
        
        responses.append(ReportResponse(
            id=report.id,
            reporter_id=report.reporter_id,
            listing_id=report.listing_id,
            category=report.category,
            details=report.details,
            status=report.status,
            reviewed_by=report.reviewed_by,
            reviewed_at=report.reviewed_at,
            action=report.action,
            created_at=report.created_at,
            listing_title=listing_title,
            reporter_name=reporter_name
        ))
    
    return responses
