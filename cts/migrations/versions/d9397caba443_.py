"""Add TagChange model.

Revision ID: d9397caba443
Revises: d47535677af6
Create Date: 2020-05-19 11:09:51.358542

"""

# revision identifiers, used by Alembic.
revision = 'd9397caba443'
down_revision = 'd47535677af6'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_table('tag_changes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('time', sa.DateTime(), nullable=False),
    sa.Column('tag_id', sa.Integer(), nullable=False),
    sa.Column('action', sa.String(), nullable=True),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('message', sa.String(), nullable=True),
    sa.Column('user_data', sa.String(), nullable=True),
    sa.ForeignKeyConstraint(['tag_id'], ['tags.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    op.drop_table('tag_changes')
