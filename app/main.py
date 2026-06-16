"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.api import users, auth, listings, search, bookmarks, conversations, messages, leads, moderation, reports, maps

settings = get_settings()

app = FastAPI(
    title="Real Estate & Renting Platform API",
    description="API for real estate listings, rentals, and PG accommodations",
    version="1.0.0",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.debug else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(users.router)
app.include_router(auth.router)
app.include_router(listings.router)
app.include_router(search.router)
app.include_router(bookmarks.router)
app.include_router(conversations.router)
app.include_router(messages.router)
app.include_router(leads.router)
app.include_router(moderation.router)
app.include_router(reports.router)
app.include_router(maps.router, prefix="/api/v1/maps", tags=["maps"])


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "environment": settings.environment}


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Real Estate & Renting Platform API",
        "version": "1.0.0",
        "docs": "/docs",
    }
