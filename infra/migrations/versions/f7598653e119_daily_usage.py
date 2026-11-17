"""설치 계정별 하루 리뷰 실행 횟수 테이블을 추가한다."""

import sqlalchemy as sa
from alembic import op

revision = "f7598653e119"
down_revision = "dd139bf4b511"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "daily_usage",
        sa.Column("installation_id", sa.BigInteger(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["installation_id"], ["installations.id"]),
        sa.PrimaryKeyConstraint("installation_id", "day"),
    )


def downgrade():
    op.drop_table("daily_usage")
