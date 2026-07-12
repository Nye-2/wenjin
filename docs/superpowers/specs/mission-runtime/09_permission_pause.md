# 09 Permission / Pause Spec

Status: Implemented
Updated: 2026-07-11

Implementation outcome: permission/question/budget waits are durable Mission pauses with owner-scoped resolution and wakeup. Review remains a separate status axis. No hidden tool-specific waiting state is authoritative.
Depends on: `02_mission_runtime.md`, `07_review_commit_runtime.md`, `10_sandbox_vnext.md`

## Goal

Unify approvals, user questions, permission escalation, external data access, and review waits as mission-level pause/resume. No tool, frontend component, or old execution path should implement its own hidden waiting logic.

## Current Code Anchors

| Current file | Current responsibility | Target action |
|---|---|---|
| `backend/src/agents/middlewares/*` | Chat-time context, tool handling, loop detection | Keep only chat-safe middleware; move durable approvals to MissionRuntime |
| `backend/src/agents/harness/command_audit.py` | Sandbox command policy and decision metadata | Keep as ToolOrchestrator policy evidence |
| `backend/src/agents/harness/contracts.py` | Harness policy fields | Merge into ToolPolicy/PermissionPolicy |
| frontend review/change panels | User checkbox decisions | Rebind to ReviewDecision and PermissionRequest surfaces |

## Request Types

```text
PermissionRequest
ToolApprovalRequest
UserQuestionRequest
ExternalDataAccessRequest
BudgetConfirmationRequest
```

All non-review requests are represented as immutable MissionItems and summarized in `MissionRun.snapshot_json.pending_request`. User review is represented by MissionReviewItems; only an in-loop decision that must precede more agent work also creates a pause request.

## User Decisions

```text
allow_once
allow_for_mission
reject
revise_and_continue
ask_more
cancel_mission
```

For review items, user actions map through ReviewCommitRuntime rather than becoming ad hoc row statuses:

```text
accept
reject
needs_more_evidence
regenerate
save_draft_only
```

Only `pending | accepted | rejected | needs_more_evidence | committed | superseded` are persisted MissionReviewItem statuses.

## Permission Policy

Permission checks happen before side effects:

```text
tool name
operation
target room/path
risk level
network profile
secret access
external account/session use
user review mode
mission policy
billing scope
```

Policy must fail closed for unknown high-risk operations.

## Pause Semantics

Pause writes:

```text
MissionItem(type=pause_request, phase=completed)
MissionRun.status=waiting
MissionRun.snapshot_json.waiting_reason
pending_request_json
```

Resume writes:

```text
MissionItem(type=resume_input, phase=completed)
MissionRun.status=running
```

Resume must include request id to avoid applying a decision to the wrong pending request.

A completed MissionRun may retain pending MissionReviewItems without reopening execution. MissionCommit progress is a separate axis and never sets MissionRun to `committing`.

## Deferred Tool Pattern

Tool proposal:

```text
tool_name
validated_args
tool_call_id
risk_reason
preview
recommended_decision
```

If approved, MissionRuntime executes or resumes the tool call and appends a normal tool result item. If rejected, model receives structured rejection and replans.

## UX Copy

User-facing language:

- "需要确认是否访问外部来源"
- "这会写入论文草稿，先确认"
- "这条论断缺少可靠证据，建议补证"
- "需要联网安装依赖"
- "本次任务需要消耗积分，确认后继续"

Avoid:

- `blocked`
- `permission_denied`
- `schema`
- raw command line by default

Advanced view may show technical detail.

## Billing Pause

Credit and budget checks are mission-level pause decisions, not hidden launch-feature behavior.

Rules:

- Insufficient credits creates `BudgetConfirmationRequest` or a user-facing budget notice.
- User approval attaches a mission-bound reservation id before continuing.
- Rejection cancels or narrows the mission according to user intent.
- ChatTurnRun cannot reserve feature-task credits.
- Budget pause state must refresh from MissionRun snapshot.

## Tests

- Unknown high-risk tool pauses or fails closed.
- Approved once does not persist to future missions.
- Approved for mission is scoped to mission id.
- Resume request id mismatch is rejected.
- Tool rejection causes replanning, not mission crash.
- Permission request survives refresh.
- Frontend cannot approve a request absent from backend snapshot.
- Budget pause cannot be bypassed by retrying the same ChatTurnRun.
