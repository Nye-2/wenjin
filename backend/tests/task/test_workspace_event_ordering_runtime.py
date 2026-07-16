"""Runtime checks for frontend workspace event monotonicity helpers."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
FRONTEND_DIR = REPO_ROOT / "frontend"
TSX_PACKAGE = FRONTEND_DIR / "node_modules" / "tsx"


def _run_helper(code: str) -> list[dict[str, object]]:
    assert TSX_PACKAGE.exists(), "tsx package is required for frontend runtime tests"
    completed = subprocess.run(
        ["node", "--import", "tsx", "-e", code],
        cwd=FRONTEND_DIR,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def test_workspace_activity_upsert_rejects_stale_snapshot() -> None:
    result = _run_helper(
        'const __ordering = await import("./lib/workspace-event-ordering.ts");'
        "const { upsertWorkspaceActivityList } = __ordering.default ?? __ordering;"
        'const existing = [{'
        '  id: "mission:1", kind: "mission", workspace_id: "ws-1", occurred_at: "2026-03-25T10:00:00Z",'
        '  title: "Literature Review", summary: "Completed", status: "completed", thread_id: "thread-1",'
        '  mission_id: "1", mission_policy_id: "sci.v1", metadata: { progress: 100 }'
        '}];'
        'const incoming = {'
        '  id: "mission:1", kind: "mission", workspace_id: "ws-1", occurred_at: "2026-03-25T09:59:00Z",'
        '  title: "Literature Review", summary: "Running", status: "running", thread_id: "thread-1",'
        '  mission_id: "1", mission_policy_id: "sci.v1", metadata: { progress: 30 }'
        '};'
        'console.log(JSON.stringify(upsertWorkspaceActivityList(existing, incoming, 40)));'
    )

    assert result[0]["status"] == "completed"
    assert result[0]["summary"] == "Completed"


def test_thread_summary_upsert_rejects_stale_snapshot() -> None:
    result = _run_helper(
        'const __ordering = await import("./lib/workspace-event-ordering.ts");'
        "const { upsertThreadSummaryList } = __ordering.default ?? __ordering;"
        'const existing = [{'
        '  id: "thread-1", workspace_id: "ws-1", title: "Main", model: "default",'
        '  message_count: 4, last_message_preview: "latest", last_message_role: "assistant",'
        '  created_at: "2026-03-25T00:00:00Z", updated_at: "2026-03-25T10:00:00Z"'
        '}];'
        'const incoming = {'
        '  id: "thread-1", workspace_id: "ws-1", title: "Main", model: "default",'
        '  message_count: 2, last_message_preview: "stale", last_message_role: "assistant",'
        '  created_at: "2026-03-25T00:00:00Z", updated_at: "2026-03-25T09:59:00Z"'
        '};'
        'console.log(JSON.stringify(upsertThreadSummaryList(existing, incoming)));'
    )

    assert result[0]["message_count"] == 4
    assert result[0]["last_message_preview"] == "latest"
