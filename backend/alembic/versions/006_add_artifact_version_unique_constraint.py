"""add artifact version unique constraint

Revision ID: 006_artifact_version_unique
Revises: 005_credit_dashboard
Create Date: 2026-03-17

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers
revision: str = "006_artifact_version_unique"
down_revision: Union[str, None] = "005_credit_dashboard"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Normalize existing duplicate versions before enabling DB-level uniqueness.
    op.execute(
        """
        WITH duplicate_rows AS (
            SELECT
                id,
                workspace_id,
                type,
                title,
                version,
                created_at,
                ROW_NUMBER() OVER (
                    PARTITION BY workspace_id, type, title, version
                    ORDER BY created_at, id
                ) AS duplicate_rank,
                MAX(version) OVER (
                    PARTITION BY workspace_id, type, title
                ) AS max_version
            FROM artifacts
            WHERE title IS NOT NULL
        ),
        to_fix AS (
            SELECT
                id,
                max_version + ROW_NUMBER() OVER (
                    PARTITION BY workspace_id, type, title
                    ORDER BY version, created_at, id
                ) AS new_version
            FROM duplicate_rows
            WHERE duplicate_rank > 1
        )
        UPDATE artifacts AS a
        SET version = to_fix.new_version
        FROM to_fix
        WHERE a.id = to_fix.id
        """
    )

    op.create_unique_constraint(
        "uq_artifacts_workspace_type_title_version",
        "artifacts",
        ["workspace_id", "type", "title", "version"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        "uq_artifacts_workspace_type_title_version",
        "artifacts",
        type_="unique",
    )
