"""Create the v0.1 schema and synchronized full-text memory index."""

import sqlalchemy as sa
from alembic import op

revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None


def identity() -> list[sa.Column[object]]:
    return [
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.Float(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "memories", *identity(),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("allow_remote", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.Float(), nullable=False),
    )
    op.create_table("conversations", *identity())
    op.create_table(
        "episodes", *identity(),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("resource_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("context_refs", sa.JSON(), nullable=False),
        sa.Column("outcome", sa.JSON(), nullable=False),
        sa.Column("completed_at", sa.Float()),
    )
    op.create_table(
        "messages", *identity(),
        sa.Column(
            "conversation_id", sa.String(), sa.ForeignKey("conversations.id"), nullable=False
        ),
        sa.Column("episode_id", sa.String(), sa.ForeignKey("episodes.id"), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
    )
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])
    op.create_index("ix_messages_episode_id", "messages", ["episode_id"])
    op.create_index(
        "ix_messages_conversation_created", "messages", ["conversation_id", "created_at"]
    )
    op.create_table(
        "tasks", *identity(),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.Float()),
        sa.Column("error", sa.String()),
    )
    op.create_table(
        "actions", *identity(),
        sa.Column("task_id", sa.String(), sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("tool", sa.String(), nullable=False),
        sa.Column("arguments", sa.JSON(), nullable=False),
        sa.Column("digest", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("result", sa.JSON()),
        sa.Column("error", sa.String()),
        sa.UniqueConstraint("task_id", "position"),
    )
    op.create_index("ix_actions_task_id", "actions", ["task_id"])
    op.create_table(
        "approvals", *identity(),
        sa.Column(
            "action_id", sa.String(), sa.ForeignKey("actions.id"), nullable=False, unique=True
        ),
        sa.Column("digest", sa.String(), nullable=False),
        sa.Column("expires_at", sa.Float(), nullable=False),
        sa.Column("consumed_at", sa.Float()),
    )
    op.create_table(
        "consents", *identity(),
        sa.Column("scope", sa.String(), nullable=False),
        sa.Column("expires_at", sa.Float(), nullable=False),
        sa.Column("revoked_at", sa.Float()),
    )
    op.create_table(
        "observations", *identity(),
        sa.Column("consent_id", sa.String(), sa.ForeignKey("consents.id"), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
    )
    op.create_table(
        "feedback", *identity(),
        sa.Column("target_type", sa.String(), nullable=False),
        sa.Column("target_id", sa.String(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("correction", sa.Text()),
        sa.UniqueConstraint("target_type", "target_id"),
    )
    op.create_table(
        "audit_events", *identity(),
        sa.Column("event", sa.String(), nullable=False),
        sa.Column("resource_id", sa.String(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
    )
    op.execute("CREATE VIRTUAL TABLE memory_fts USING fts5(memory_id UNINDEXED, content)")
    op.execute("""
        CREATE TRIGGER memories_insert AFTER INSERT ON memories BEGIN
            INSERT INTO memory_fts(memory_id, content) VALUES (new.id, new.content);
        END
    """)
    op.execute("""
        CREATE TRIGGER memories_delete AFTER DELETE ON memories BEGIN
            DELETE FROM memory_fts WHERE memory_id = old.id;
        END
    """)
    op.execute("""
        CREATE TRIGGER memories_update AFTER UPDATE ON memories BEGIN
            DELETE FROM memory_fts WHERE memory_id = old.id;
            INSERT INTO memory_fts(memory_id, content) VALUES (new.id, new.content);
        END
    """)


def downgrade() -> None:
    for trigger in ("memories_insert", "memories_delete", "memories_update"):
        op.execute(f"DROP TRIGGER {trigger}")
    op.execute("DROP TABLE memory_fts")
    for table in (
        "audit_events", "feedback", "observations", "consents", "approvals",
        "actions", "tasks", "messages", "episodes", "conversations", "memories",
    ):
        op.drop_table(table)
