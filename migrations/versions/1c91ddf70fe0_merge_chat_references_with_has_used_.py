"""merge chat references with has_used_trial heads

Revision ID: 1c91ddf70fe0
Revises: 330fa9731a9d, b2c3d4e5f6a7
Create Date: 2025-11-19 19:24:33.843035

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1c91ddf70fe0'
down_revision = ('330fa9731a9d', 'b2c3d4e5f6a7')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
