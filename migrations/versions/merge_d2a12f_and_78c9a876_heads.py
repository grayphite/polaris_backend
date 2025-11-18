"""
Merge heads 9a1b3d2f6c7e and 78c9a87636b2

Revision ID: 3b7f4c2d9e10
Revises: 9a1b3d2f6c7e, 78c9a87636b2
Create Date: 2025-10-31 00:05:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '3b7f4c2d9e10'
down_revision = ('9a1b3d2f6c7e', '78c9a87636b2')
branch_labels = None
depends_on = None


def upgrade():
    # This is a merge migration; no schema changes are required.
    pass


def downgrade():
    # Downgrade cannot be sensibly automated for a merge; no action.
    pass


