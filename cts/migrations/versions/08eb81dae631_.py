"""Add ComposeInfo fields to composes table.

Revision ID: 08eb81dae631
Revises: dd4d36995e1c
Create Date: 2020-05-18 13:18:45.534178

"""

# revision identifiers, used by Alembic.
revision = "08eb81dae631"
down_revision = "dd4d36995e1c"

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column(
        "composes", sa.Column("base_product_name", sa.String(), nullable=True)
    )
    op.add_column(
        "composes", sa.Column("base_product_short", sa.String(), nullable=True)
    )
    op.add_column(
        "composes", sa.Column("base_product_type", sa.String(), nullable=True)
    )
    op.add_column(
        "composes", sa.Column("base_product_version", sa.String(), nullable=True)
    )
    op.add_column("composes", sa.Column("builder", sa.String(), nullable=True))
    op.add_column("composes", sa.Column("date", sa.String(), nullable=True))
    op.add_column("composes", sa.Column("final", sa.Boolean(), nullable=True))
    op.add_column("composes", sa.Column("label", sa.String(), nullable=True))
    op.add_column(
        "composes", sa.Column("release_internal", sa.Boolean(), nullable=True)
    )
    op.add_column(
        "composes", sa.Column("release_is_layered", sa.Boolean(), nullable=True)
    )
    op.add_column("composes", sa.Column("release_name", sa.String(), nullable=True))
    op.add_column("composes", sa.Column("release_short", sa.String(), nullable=True))
    op.add_column("composes", sa.Column("release_type", sa.String(), nullable=True))
    op.add_column("composes", sa.Column("release_version", sa.String(), nullable=True))
    op.add_column("composes", sa.Column("respin", sa.Integer(), nullable=True))
    op.add_column("composes", sa.Column("type", sa.String(), nullable=True))


def downgrade():
    op.drop_column("composes", "type")
    op.drop_column("composes", "respin")
    op.drop_column("composes", "release_version")
    op.drop_column("composes", "release_type")
    op.drop_column("composes", "release_short")
    op.drop_column("composes", "release_name")
    op.drop_column("composes", "release_is_layered")
    op.drop_column("composes", "release_internal")
    op.drop_column("composes", "label")
    op.drop_column("composes", "final")
    op.drop_column("composes", "date")
    op.drop_column("composes", "builder")
    op.drop_column("composes", "base_product_version")
    op.drop_column("composes", "base_product_type")
    op.drop_column("composes", "base_product_short")
    op.drop_column("composes", "base_product_name")
