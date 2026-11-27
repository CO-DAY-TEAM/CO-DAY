"""리뷰에 PR 본문을 저장한다."""

import sqlalchemy as sa
from alembic import op

revision = "8fb2c8f1d4a6"
down_revision = "f7598653e119"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("reviews", sa.Column("pr_body", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("reviews", "pr_body")
