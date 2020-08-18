"""Add Compose.parents and Compose.children.

Revision ID: e2af98ac38f5
Revises: 3f4b23f8c3d5
Create Date: 2020-08-13 08:30:00.283792

"""

# revision identifiers, used by Alembic.
revision = 'e2af98ac38f5'
down_revision = '3f4b23f8c3d5'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_table('composes_to_composes',
    sa.Column('parent_compose_id', sa.String(), nullable=False),
    sa.Column('child_compose_id', sa.String(), nullable=False),
    sa.ForeignKeyConstraint(['child_compose_id'], ['composes.id'], ),
    sa.ForeignKeyConstraint(['parent_compose_id'], ['composes.id'], ),
    sa.UniqueConstraint('parent_compose_id', 'child_compose_id', name='unique_composes')
    )


def downgrade():
    op.drop_table('composes_to_composes')
