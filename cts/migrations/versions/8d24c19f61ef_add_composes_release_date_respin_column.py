"""add_composes_release_date_respin_column

Revision ID: 8d24c19f61ef
Revises: 0720c0281233
Create Date: 2024-06-13 10:13:33.413878

"""

# revision identifiers, used by Alembic.
revision = "8d24c19f61ef"
down_revision = "0720c0281233"

from alembic import op
import sqlalchemy as sa


def upgrade():
    with op.batch_alter_table("composes", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("release_date_respin", sa.String(), nullable=True)
        )
        batch_op.create_unique_constraint(
            "uq_composes_release_date_respin", ["release_date_respin"]
        )
    op.execute("""
        UPDATE composes
        SET release_date_respin = CONCAT_WS('-', release_short, release_version, date_respin)
        WHERE date_respin IS NOT NULL
        """)


def downgrade():
    with op.batch_alter_table("composes", schema=None) as batch_op:
        batch_op.drop_constraint("uq_composes_release_date_respin", type_="unique")
        batch_op.drop_column("release_date_respin")
