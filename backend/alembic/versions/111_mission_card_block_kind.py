"""Allow the mission_card conversation block kind.

Revision ID: 111_mission_card_block_kind
Revises: 110_deduplicate_mission_references
"""

from alembic import op

revision = "111_mission_card_block_kind"
down_revision = "110_deduplicate_mission_references"
branch_labels = None
depends_on = None

_LEGACY_BLOCK_TYPES = (
    "text",
    "thinking",
    "status_line",
    "question_card",
    "result_card",
    "tool_invocation",
    "tool_result",
)

_BLOCK_TYPES = (*_LEGACY_BLOCK_TYPES, "mission_card")


def _constraint_sql(block_types: tuple[str, ...]) -> str:
    return "block_type in (" + ", ".join(f"'{kind}'" for kind in block_types) + ")"


def upgrade() -> None:
    op.drop_constraint(
        "ck_message_blocks_block_type",
        "message_blocks",
        type_="check",
    )
    op.create_check_constraint(
        "ck_message_blocks_block_type",
        "message_blocks",
        _constraint_sql(_BLOCK_TYPES),
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_message_blocks_block_type",
        "message_blocks",
        type_="check",
    )
    op.create_check_constraint(
        "ck_message_blocks_block_type",
        "message_blocks",
        _constraint_sql(_LEGACY_BLOCK_TYPES),
    )
