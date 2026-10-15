"""초기 데이터베이스 스키마를 생성한다."""

import sqlalchemy as sa
from alembic import op

revision = "dd139bf4b511"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Alembic이 자동 생성한 마이그레이션 명령이며, 적용 전에 내용을 확인한다.
    op.create_table(
        "deliveries",
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("event", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_deliveries_status"), "deliveries", ["status"], unique=False)
    op.create_table(
        "installations",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("login", sa.String(length=255), nullable=False),
        sa.Column("account_type", sa.String(length=32), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("paused", sa.Boolean(), nullable=False),
        sa.Column("settings", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "login_sessions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("login", sa.String(length=255), nullable=False),
        sa.Column("token", sa.Text(), nullable=False),
        sa.Column("refresh_token", sa.Text(), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("csrf", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "oauth_states",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("verifier", sa.String(length=128), nullable=False),
        sa.Column("return_to", sa.String(length=2048), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "repositories",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("installation_id", sa.BigInteger(), nullable=False),
        sa.Column("full_name", sa.String(length=512), nullable=False),
        sa.Column("private", sa.Boolean(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("use_common", sa.Boolean(), nullable=False),
        sa.Column("settings", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(
            ["installation_id"],
            ["installations.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_repositories_installation_id"), "repositories", ["installation_id"], unique=False
    )
    op.create_table(
        "posted_findings",
        sa.Column("repository_id", sa.BigInteger(), nullable=False),
        sa.Column("pr_number", sa.Integer(), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("github_review_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["repository_id"],
            ["repositories.id"],
        ),
        sa.PrimaryKeyConstraint("repository_id", "pr_number", "fingerprint"),
    )
    op.create_table(
        "pull_requests",
        sa.Column("repository_id", sa.BigInteger(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("head_sha", sa.String(length=64), nullable=False),
        sa.Column("progress_comment_id", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(
            ["repository_id"],
            ["repositories.id"],
        ),
        sa.PrimaryKeyConstraint("repository_id", "number"),
    )
    op.create_table(
        "reviews",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("request_key", sa.String(length=255), nullable=False),
        sa.Column("repository_id", sa.BigInteger(), nullable=False),
        sa.Column("pr_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("head_sha", sa.String(length=64), nullable=False),
        sa.Column("base_sha", sa.String(length=64), nullable=False),
        sa.Column("settings", sa.JSON(), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("trigger", sa.String(length=16), nullable=False),
        sa.Column("requester", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("stage", sa.String(length=32), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recoveries", sa.Integer(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("ai_calls", sa.Integer(), nullable=False),
        sa.Column("input", sa.JSON(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("publication", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(
            ["repository_id"],
            ["repositories.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_key"),
    )
    op.create_index(op.f("ix_reviews_repository_id"), "reviews", ["repository_id"], unique=False)
    op.create_index(op.f("ix_reviews_status"), "reviews", ["status"], unique=False)
    op.create_index(
        "one_active_review_per_pr",
        "reviews",
        ["repository_id", "pr_number"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running')"),
        sqlite_where=sa.text("status IN ('queued', 'running')"),
    )
    op.create_table(
        "unit_results",
        sa.Column("review_id", sa.String(length=36), nullable=False),
        sa.Column("unit", sa.Integer(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["review_id"],
            ["reviews.id"],
        ),
        sa.PrimaryKeyConstraint("review_id", "unit"),
    )
    # Alembic 자동 생성 명령 끝


def downgrade():
    # Alembic이 자동 생성한 마이그레이션 명령이며, 적용 전에 내용을 확인한다.
    op.drop_table("unit_results")
    op.drop_index(
        "one_active_review_per_pr",
        table_name="reviews",
        postgresql_where=sa.text("status IN ('queued', 'running')"),
        sqlite_where=sa.text("status IN ('queued', 'running')"),
    )
    op.drop_index(op.f("ix_reviews_status"), table_name="reviews")
    op.drop_index(op.f("ix_reviews_repository_id"), table_name="reviews")
    op.drop_table("reviews")
    op.drop_table("pull_requests")
    op.drop_table("posted_findings")
    op.drop_index(op.f("ix_repositories_installation_id"), table_name="repositories")
    op.drop_table("repositories")
    op.drop_table("oauth_states")
    op.drop_table("login_sessions")
    op.drop_table("installations")
    op.drop_index(op.f("ix_deliveries_status"), table_name="deliveries")
    op.drop_table("deliveries")
    # Alembic 자동 생성 명령 끝
