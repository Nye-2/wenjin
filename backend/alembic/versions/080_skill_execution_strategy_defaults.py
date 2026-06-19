"""add default skill execution strategies

Revision ID: 080_skill_execution_strategy_defaults
Revises: 079_workspace_sandbox_convergence
Create Date: 2026-06-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "080_skill_execution_strategy_defaults"
down_revision: str | None = "079_workspace_sandbox_convergence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    _apply_strategy_defaults(
        """
        VALUES
            ('task-scope-planner', jsonb_build_object('mode', 'direct')),
            ('query-planner', jsonb_build_object('mode', 'direct')),
            (
                'literature-synthesizer',
                jsonb_build_object(
                    'mode', 'direct_when_upstream_evidence',
                    'min_evidence_items', 1
                )
            )
        """
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            WITH strategy(skill_id, strategy_json) AS (
                VALUES
                    ('task-scope-planner', jsonb_build_object('mode', 'direct')),
                    ('query-planner', jsonb_build_object('mode', 'direct')),
                    (
                        'literature-synthesizer',
                        jsonb_build_object(
                            'mode', 'direct_when_upstream_evidence',
                            'min_evidence_items', 1
                        )
                    )
            ),
            updated AS (
                UPDATE capability_skills AS skill
                SET config = skill.config #- '{extensions,execution_strategy}'
                FROM strategy
                WHERE skill.id = strategy.skill_id
                  AND skill.config #> '{extensions,execution_strategy}' = strategy.strategy_json
                RETURNING skill.id, skill.config
            )
            UPDATE capability_skills AS skill
            SET skill_json = jsonb_set(
                coalesce(skill.skill_json, '{}'::jsonb),
                '{config}',
                updated.config,
                true
            )
            FROM updated
            WHERE skill.id = updated.id
            """
        )
    )


def _apply_strategy_defaults(values_sql: str) -> None:
    op.execute(
        sa.text(
            f"""
            WITH strategy(skill_id, strategy_json) AS (
                {values_sql}
            ),
            patched_config AS (
                SELECT
                    skill.id,
                    jsonb_set(
                        jsonb_set(
                            coalesce(skill.config, '{{}}'::jsonb),
                            '{{extensions}}',
                            coalesce(skill.config -> 'extensions', '{{}}'::jsonb),
                            true
                        ),
                        '{{extensions,execution_strategy}}',
                        strategy.strategy_json,
                        true
                    ) AS config
                FROM capability_skills AS skill
                JOIN strategy ON strategy.skill_id = skill.id
                WHERE skill.config #> '{{extensions,execution_strategy}}' IS NULL
            ),
            updated AS (
                UPDATE capability_skills AS skill
                SET config = patched_config.config
                FROM patched_config
                WHERE skill.id = patched_config.id
                RETURNING skill.id, skill.config
            )
            UPDATE capability_skills AS skill
            SET skill_json = jsonb_set(
                coalesce(skill.skill_json, '{{}}'::jsonb),
                '{{config}}',
                updated.config,
                true
            )
            FROM updated
            WHERE skill.id = updated.id
            """
        )
    )
