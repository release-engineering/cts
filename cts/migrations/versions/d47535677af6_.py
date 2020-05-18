"""Add tags table and relations.

Revision ID: d47535677af6
Revises: 08eb81dae631
Create Date: 2020-05-18 13:24:34.461284

"""

# revision identifiers, used by Alembic.
revision = 'd47535677af6'
down_revision = '08eb81dae631'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_table('tags',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('description', sa.String(), nullable=False),
    sa.Column('documentation', sa.String(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('taggers',
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('tag_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['tag_id'], ['tags.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.UniqueConstraint('user_id', 'tag_id', name='unique_taggers')
    )
    op.create_table('tags_to_composes',
    sa.Column('compose_id', sa.Integer(), nullable=False),
    sa.Column('tag_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['compose_id'], ['composes.id'], ),
    sa.ForeignKeyConstraint(['tag_id'], ['tags.id'], ),
    sa.UniqueConstraint('compose_id', 'tag_id', name='unique_tags')
    )
    op.create_table('untaggers',
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('tag_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['tag_id'], ['tags.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.UniqueConstraint('user_id', 'tag_id', name='unique_untaggers')
    )


def downgrade():
    op.drop_table('untaggers')
    op.drop_table('tags_to_composes')
    op.drop_table('taggers')
    op.drop_table('tags')
