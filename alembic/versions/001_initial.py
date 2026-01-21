"""Initial migration - create all tables

Revision ID: 001_initial
Revises: 
Create Date: 2026-01-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create users table
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('email', sa.String(255), unique=True, nullable=False),
        sa.Column('phone', sa.String(20), unique=True, nullable=True),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('profile_photo', sa.Text(), nullable=True),
        sa.Column('bio', sa.Text(), nullable=True),
        sa.Column('roles', postgresql.ARRAY(sa.String()), nullable=False, server_default='{"seeker"}'),
        sa.Column('verified', sa.Boolean(), default=False),
        sa.Column('status', sa.String(20), default='active'),
        sa.Column('privacy_settings', postgresql.JSONB(), nullable=True),
        sa.Column('failed_login_attempts', sa.Integer(), default=0),
        sa.Column('locked_until', sa.TIMESTAMP(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.TIMESTAMP(), nullable=False, server_default=sa.func.now()),
        sa.Column('last_login_at', sa.TIMESTAMP(), nullable=True),
    )
    op.create_index('ix_users_email', 'users', ['email'])
    op.create_index('ix_users_phone', 'users', ['phone'])
    op.create_index('ix_users_status', 'users', ['status'])

    # Create listings table
    op.create_table(
        'listings',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('owner_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('type', sa.String(20), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('price_amount', sa.DECIMAL(15, 2), nullable=False),
        sa.Column('price_currency', sa.String(3), default='INR'),
        sa.Column('price_type', sa.String(20), default='sale'),
        sa.Column('address', sa.Text(), nullable=True),
        sa.Column('city', sa.String(100), nullable=True),
        sa.Column('state', sa.String(100), nullable=True),
        sa.Column('country', sa.String(100), default='India'),
        sa.Column('postal_code', sa.String(20), nullable=True),
        sa.Column('latitude', sa.Float(), nullable=True),
        sa.Column('longitude', sa.Float(), nullable=True),
        sa.Column('size', sa.DECIMAL(10, 2), nullable=True),
        sa.Column('amenities', postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column('images', postgresql.JSONB(), nullable=True),
        sa.Column('status', sa.String(20), default='pending_review'),
        sa.Column('moderation_status', sa.String(20), default='pending'),
        sa.Column('rejection_reason', sa.Text(), nullable=True),
        sa.Column('view_count', sa.Integer(), default=0),
        sa.Column('lead_count', sa.Integer(), default=0),
        sa.Column('promoted', sa.Boolean(), default=False),
        sa.Column('promotion_expires_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('expires_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.TIMESTAMP(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_listings_status', 'listings', ['status'])
    op.create_index('ix_listings_type', 'listings', ['type'])
    op.create_index('ix_listings_created_at', 'listings', ['created_at'])
    op.create_index('ix_listings_location', 'listings', ['latitude', 'longitude'])

    # Create conversations table
    op.create_table(
        'conversations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('listing_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('listings.id', ondelete='SET NULL'), nullable=True),
        sa.Column('participants', postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=False),
        sa.Column('last_message_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_conversations_listing_id', 'conversations', ['listing_id'])

    # Create messages table
    op.create_table(
        'messages',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('conversation_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('conversations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('sender_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('media_url', sa.Text(), nullable=True),
        sa.Column('sent_at', sa.TIMESTAMP(), nullable=False, server_default=sa.func.now()),
        sa.Column('delivered_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('read_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('status', sa.String(20), default='sent'),
    )
    op.create_index('ix_messages_conversation_id', 'messages', ['conversation_id'])
    op.create_index('ix_messages_sent_at', 'messages', ['sent_at'])

    # Create bookmarks table (composite primary key)
    op.create_table(
        'bookmarks',
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('listing_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('listings.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=False, server_default=sa.func.now()),
    )

    # Create reports table
    op.create_table(
        'reports',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('reporter_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('listing_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('listings.id', ondelete='CASCADE'), nullable=False),
        sa.Column('category', sa.String(50), nullable=False),
        sa.Column('details', sa.Text(), nullable=True),
        sa.Column('status', sa.String(20), default='pending'),
        sa.Column('reviewed_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('reviewed_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('action', sa.String(50), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_reports_listing_id', 'reports', ['listing_id'])
    op.create_index('ix_reports_status', 'reports', ['status'])

    # Create leads table
    op.create_table(
        'leads',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('listing_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('listings.id', ondelete='CASCADE'), nullable=False),
        sa.Column('seeker_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('owner_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('conversation_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('conversations.id', ondelete='SET NULL'), nullable=True),
        sa.Column('status', sa.String(30), default='new'),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.TIMESTAMP(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_leads_listing_id', 'leads', ['listing_id'])
    op.create_index('ix_leads_seeker_id', 'leads', ['seeker_id'])
    op.create_index('ix_leads_owner_id', 'leads', ['owner_id'])
    op.create_index('ix_leads_status', 'leads', ['status'])

    # Create saved_searches table
    op.create_table(
        'saved_searches',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('criteria', postgresql.JSONB(), nullable=False),
        sa.Column('notification_enabled', sa.Boolean(), default=True),
        sa.Column('frequency', sa.String(20), default='instant'),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_saved_searches_user_id', 'saved_searches', ['user_id'])

    # Create view_history table
    op.create_table(
        'view_history',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('listing_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('listings.id', ondelete='CASCADE'), nullable=False),
        sa.Column('viewed_at', sa.TIMESTAMP(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_view_history_user_id', 'view_history', ['user_id'])

    # Create user_blocks table (composite primary key)
    op.create_table(
        'user_blocks',
        sa.Column('blocker_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('blocked_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('user_blocks')
    op.drop_table('view_history')
    op.drop_table('saved_searches')
    op.drop_table('leads')
    op.drop_table('reports')
    op.drop_table('bookmarks')
    op.drop_table('messages')
    op.drop_table('conversations')
    op.drop_table('listings')
    op.drop_table('users')
