"""Add geography column for spatial queries

Revision ID: 002_add_geography
Revises: 001_initial
Create Date: 2026-01-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from geoalchemy2 import Geography

# revision identifiers, used by Alembic.
revision: str = '002_add_geography'
down_revision: Union[str, None] = '001_initial'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable PostGIS extension
    op.execute('CREATE EXTENSION IF NOT EXISTS postgis')
    
    # Add geography column for efficient spatial queries
    op.add_column(
        'listings',
        sa.Column('location', Geography(geometry_type='POINT', srid=4326), nullable=True)
    )
    
    # Create spatial index for fast radius queries
    op.create_index(
        'ix_listings_location_gist',
        'listings',
        ['location'],
        postgresql_using='gist'
    )
    
    # Populate location from existing latitude/longitude data
    op.execute('''
        UPDATE listings 
        SET location = ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography
        WHERE latitude IS NOT NULL AND longitude IS NOT NULL
    ''')
    
    # Create function to auto-sync location when lat/lng change
    op.execute('''
        CREATE OR REPLACE FUNCTION update_listing_location()
        RETURNS TRIGGER AS $$
        BEGIN
            IF NEW.latitude IS NOT NULL AND NEW.longitude IS NOT NULL THEN
                NEW.location := ST_SetSRID(ST_MakePoint(NEW.longitude, NEW.latitude), 4326)::geography;
            ELSE
                NEW.location := NULL;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    ''')
    
    # Create trigger to auto-update location
    op.execute('''
        CREATE TRIGGER trigger_update_listing_location
        BEFORE INSERT OR UPDATE OF latitude, longitude ON listings
        FOR EACH ROW
        EXECUTE FUNCTION update_listing_location();
    ''')


def downgrade() -> None:
    # Drop trigger and function
    op.execute('DROP TRIGGER IF EXISTS trigger_update_listing_location ON listings')
    op.execute('DROP FUNCTION IF EXISTS update_listing_location()')
    
    # Drop index and column
    op.drop_index('ix_listings_location_gist', table_name='listings')
    op.drop_column('listings', 'location')
