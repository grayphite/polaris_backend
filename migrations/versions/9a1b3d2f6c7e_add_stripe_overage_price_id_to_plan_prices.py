"""
add stripe_overage_price_id to plan_prices

Revision ID: 9a1b3d2f6c7e
Revises: 78c9a87636b2
Create Date: 2025-10-31 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9a1b3d2f6c7e'
down_revision = 'd2a12f31637b'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('plan_prices', sa.Column('stripe_overage_price_id', sa.String(length=100), nullable=True))
    op.create_index('ix_plan_prices_stripe_overage_price_id', 'plan_prices', ['stripe_overage_price_id'], unique=False)


def downgrade():
    op.drop_index('ix_plan_prices_stripe_overage_price_id', table_name='plan_prices')
    op.drop_column('plan_prices', 'stripe_overage_price_id')


