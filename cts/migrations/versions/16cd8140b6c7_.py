"""Add Compose.respin_of.

Revision ID: 16cd8140b6c7
Revises: e2af98ac38f5
Create Date: 2020-11-19 09:30:35.665472

"""

# revision identifiers, used by Alembic.
revision = '16cd8140b6c7'
down_revision = 'e2af98ac38f5'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column('composes', sa.Column('respin_of_id', sa.String(), nullable=True))
    op.create_foreign_key(None, 'composes', 'composes', ['respin_of_id'], ['id'])


def downgrade():
    op.drop_constraint(None, 'composes', type_='foreignkey')
    op.drop_column('composes', 'respin_of_id')
