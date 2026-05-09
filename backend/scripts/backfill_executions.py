"""Backfill script: migrate legacy data into executions table.

Usage:
    cd backend && python -m scripts.backfill_executions --dry-run
    cd backend && python -m scripts.backfill_executions --execute

This script is idempotent — running it multiple times is safe.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from sqlalchemy import text

from src.database import get_db_session

logger = logging.getLogger("backfill_executions")
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

# SQL for backfilling execution_sessions → executions
_BACKFILL_EXECUTION_SESSIONS = """
INSERT INTO executions (
    id, user_id, workspace_id, thread_id, execution_type,
    workspace_type, feature_id, entry_skill_id, status,
    params, result_summary, runtime_state, artifact_ids, next_actions,
    advisory_code, last_error, created_at, started_at, completed_at
)
SELECT
    id,
    user_id,
    workspace_id,
    thread_id,
    'feature',
    workspace_type,
    feature_id,
    entry_skill_id,
    CASE status
        WHEN 'launching' THEN 'pending'
        WHEN 'running' THEN 'running'
        WHEN 'completed' THEN 'completed'
        WHEN 'failed' THEN 'failed'
        WHEN 'advisory' THEN 'awaiting_user_input'
        WHEN 'cancelled' THEN 'cancelled'
        ELSE status
    END,
    params,
    result_summary,
    runtime_snapshot,
    artifact_ids,
    next_actions,
    advisory_code,
    last_error,
    created_at,
    started_at,
    completed_at
FROM execution_sessions
ON CONFLICT (id) DO NOTHING;
"""

# SQL for backfilling task_records → executions
_BACKFILL_TASK_RECORDS = """
INSERT INTO executions (
    id, user_id, workspace_id, thread_id, execution_type,
    feature_id, status, params, result, error, progress, message,
    runtime_state, created_at, started_at, completed_at
)
SELECT
    id,
    user_id,
    workspace_id,
    thread_id,
    CASE task_type
        WHEN 'workspace_feature' THEN 'feature'
        ELSE task_type
    END,
    feature_id,
    CASE status
        WHEN 'pending' THEN 'pending'
        WHEN 'running' THEN 'running'
        WHEN 'success' THEN 'completed'
        WHEN 'failed' THEN 'failed'
        WHEN 'cancelled' THEN 'cancelled'
        ELSE status
    END,
    payload,
    result,
    error,
    progress,
    message,
    runtime_state,
    created_at,
    started_at,
    completed_at
FROM task_records
WHERE execution_session_id IS NULL
  AND id NOT IN (SELECT id FROM executions)
ON CONFLICT (id) DO NOTHING;
"""

# SQL for backfilling workspace_run → executions
_BACKFILL_WORKSPACE_RUN = """
INSERT INTO executions (
    id, workspace_id, thread_id, execution_type, status,
    result, created_at, started_at, completed_at
)
SELECT
    id,
    workspace_id,
    thread_id,
    'chat_turn',
    CASE status
        WHEN 'success' THEN 'completed'
        ELSE COALESCE(status, 'completed')
    END,
    result_card,
    created_at,
    started_at,
    completed_at
FROM workspace_run
WHERE deleted_at IS NULL
  AND id NOT IN (SELECT id FROM executions)
ON CONFLICT (id) DO UPDATE SET
    status = EXCLUDED.status,
    result = EXCLUDED.result,
    updated_at = NOW();
"""

# SQL for adding execution_id to subagent_task_records
_BACKFILL_SUBAGENT_TASKS = """
UPDATE subagent_task_records
SET execution_id = execution_session_id
WHERE execution_session_id IN (SELECT id FROM executions)
  AND execution_id IS NULL;
"""

# Validation queries
_VALIDATE_NO_DUPLICATES = """
SELECT id, COUNT(*) as cnt FROM executions GROUP BY id HAVING COUNT(*) > 1;
"""

_VALIDATE_EXECUTION_SESSIONS = """
SELECT COUNT(*) FROM execution_sessions WHERE id NOT IN (SELECT id FROM executions);
"""

_VALIDATE_WORKSPACE_RUN = """
SELECT COUNT(*) FROM workspace_run WHERE deleted_at IS NULL AND id NOT IN (SELECT id FROM executions);
"""

_VALIDATE_SUBAGENT_TASKS = """
SELECT COUNT(*) FROM subagent_task_records WHERE execution_id IS NULL;
"""


async def _run_backfill(dry_run: bool) -> dict[str, int]:
    """Run all backfill operations and return row counts."""
    counts: dict[str, int] = {}

    async with get_db_session() as db:
        # Backfill execution_sessions
        result = await db.execute(text(_BACKFILL_EXECUTION_SESSIONS))
        counts["execution_sessions"] = result.rowcount if not dry_run else 0

        # Backfill task_records
        result = await db.execute(text(_BACKFILL_TASK_RECORDS))
        counts["task_records"] = result.rowcount if not dry_run else 0

        # Backfill workspace_run
        result = await db.execute(text(_BACKFILL_WORKSPACE_RUN))
        counts["workspace_run"] = result.rowcount if not dry_run else 0

        # Backfill subagent_task_records
        result = await db.execute(text(_BACKFILL_SUBAGENT_TASKS))
        counts["subagent_tasks"] = result.rowcount if not dry_run else 0

        if not dry_run:
            await db.commit()

    return counts


async def _validate() -> dict[str, Any]:
    """Run validation queries."""
    issues: dict[str, Any] = {}

    async with get_db_session() as db:
        # Check duplicates
        result = await db.execute(text(_VALIDATE_NO_DUPLICATES))
        duplicates = result.all()
        issues["duplicates"] = len(duplicates)
        if duplicates:
            logger.error("Found %d duplicate execution IDs!", len(duplicates))

        # Check coverage
        result = await db.execute(text(_VALIDATE_EXECUTION_SESSIONS))
        issues["missing_execution_sessions"] = result.scalar_one()

        result = await db.execute(text(_VALIDATE_WORKSPACE_RUN))
        issues["missing_workspace_run"] = result.scalar_one()

        result = await db.execute(text(_VALIDATE_SUBAGENT_TASKS))
        issues["missing_subagent_tasks"] = result.scalar_one()

    return issues


async def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill legacy data into executions table")
    parser.add_argument("--dry-run", action="store_true", help="Preview without modifying data")
    parser.add_argument("--validate-only", action="store_true", help="Only run validation queries")
    args = parser.parse_args()

    if args.validate_only:
        logger.info("Running validation only...")
        issues = await _validate()
        logger.info("Validation results: %s", issues)
        if issues["duplicates"] > 0:
            return 1
        return 0

    logger.info("Starting backfill (dry_run=%s)...", args.dry_run)

    counts = await _run_backfill(dry_run=args.dry_run)
    logger.info("Backfill counts: %s", counts)

    issues = await _validate()
    logger.info("Validation results: %s", issues)

    if issues["duplicates"] > 0:
        logger.error("BACKFILL FAILED: duplicates found")
        return 1

    if args.dry_run:
        logger.info("Dry run complete. Use --execute to apply changes.")
    else:
        logger.info("Backfill complete.")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
