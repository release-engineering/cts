"""Add compose_changes table.

Revision ID: 3f4b23f8c3d5
Revises: d9397caba443
Create Date: 2020-05-20 07:27:32.797398

"""

# revision identifiers, used by Alembic.
revision = "3f4b23f8c3d5"
down_revision = "d9397caba443"

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_table(
        "compose_changes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("time", sa.DateTime(), nullable=False),
        sa.Column("compose_id", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("message", sa.String(), nullable=True),
        sa.Column("user_data", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(
            ["compose_id"],
            ["composes.id"],
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade():
    op.drop_table("compose_changes")
