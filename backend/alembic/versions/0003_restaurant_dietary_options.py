"""Source-declared menu options, separate from cuisine and verified requirements."""

import sqlalchemy as sa

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("restaurants", sa.Column("dietary_options", sa.JSON(), nullable=False, server_default="[]"))


def downgrade():
    op.drop_column("restaurants", "dietary_options")
