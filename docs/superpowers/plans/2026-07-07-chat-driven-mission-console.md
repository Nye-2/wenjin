# Chat-Driven Mission Console Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Wenjin's default right-side capability launcher with a chat-driven Mission Console, deepen SCI/thesis research harness behavior, and make follow-up work reuse mission context instead of restarting from a static workflow card.

**Architecture:** Chat Agent remains the only user-facing task navigator. Capability v2 remains the backend mission contract for routing hints, methodology, review policy, evidence policy, and TeamKernel orchestration. `RunView` and `LiveWorkflowViewModel` remain the frontend execution projection boundary. Mission state is derived from existing execution runtime state, `TaskReport`, review packets, and `ResearchStateV1`; it must not become a second execution fact source.

**Tech Stack:** FastAPI, Pydantic v2, LangGraph, TeamKernel, pytest, Next.js 16, React 19, TypeScript, Zustand, Tailwind, Vitest.

## Global Constraints

- Keep all durable launches on the existing `chat_agent -> launch_feature -> lead_agent -> TeamKernel` path.
- Remove the default right-panel capability launch path in one pass. Do not keep a hidden duplicate launcher in `LiveWorkflowPanel`.
- Do not add a frontend capability classifier, frontend route matcher, direct execution endpoint, or feature deep-link path that bypasses Chat Agent.
- Do not add compatibility layers, parallel launch adapters, parallel mission stores, or alternate execution projections.
- Keep `run-ui-store` focused on UI focus and badges. Do not put mission content or execution facts there.
- Keep `execution-run-view.ts` as the place where raw execution/runtime/result payloads become UI-safe projection data.
- Keep view components on projected fields. Do not parse raw TeamKernel schemas inside React components.
- Use `--wjn-*` tokens for new UI surfaces. Do not introduce `--v2-*` usage, decorative backgrounds, raw log panels, or fixed technical sidebars in the default UX.
- Do not expose capability ids, route-card labels, internal schema ids, raw tool JSON, raw node payloads, or full harness graphs to normal users.
- Evidence, citation, claim, and primary document writes remain high-risk review items and must not be bulk accepted until manually reviewed.

---

## Source Inputs

- Design spec: `docs/superpowers/specs/2026-07-07-chat-driven-mission-console-design.md`
- Architecture source: `docs/current/architecture.md`
- Workspace behavior source: `docs/current/workspace-current-state.md`
- UI source: `docs/current/wenjin-research-navigation-uiux.md`
- Mission contract source: `docs/current/frontend-mission-contract.md`
- Catalog source: `docs/current/workspace-mission-catalog.md`
- AGENTS project instructions in repository root.

## Current Code Map

Frontend:

- Workspace shell: `frontend/app/(workbench)/workspaces/[id]/page.tsx`
- Chat surface: `frontend/app/(workbench)/workspaces/[id]/components/ChatPanel.tsx`
- Right workbench shell: `frontend/app/(workbench)/workspaces/[id]/components/LiveWorkflowPanel.tsx`
- Current capability grid: `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/OverviewView.tsx`
- Right workbench tabs: `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/WorkbenchHeader.tsx`
- Right workbench projection hook: `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/useLiveWorkflowViewModel.ts`
- Run projection: `frontend/lib/execution-run-view.ts`
- Workbench layout state: `frontend/stores/workbench-layout-store.ts`
- Feature API types: `frontend/lib/api/types.ts`

Backend:

- Chat Agent prompt assembly: `backend/src/agents/chat_agent/agent.py`
- Chat Agent system prompt: `backend/src/agents/chat_agent/prompts/system.py`
- Launch boundary: `backend/src/tools/builtins/launch_feature.py`
- Mission policy schema: `backend/src/services/mission_policy_schema.py`
- Research state: `backend/src/agents/harness/research_state.py`
- Team member context projection: `backend/src/agents/lead_agent/v2/team/member_context.py`
- TeamKernel runtime: `backend/src/agents/lead_agent/v2/team/kernel.py`
- Quality gates: `backend/src/agents/lead_agent/v2/team/quality_gates.py`
- Research task evaluation: `backend/src/agents/harness/research_task_eval.py`
- SCI main capability: `backend/seed/capabilities/sci/research_question_to_paper.yaml`
- SCI literature capability: `backend/seed/capabilities/sci/sci_literature_positioning.yaml`
- Thesis research pack: `backend/seed/capabilities/thesis/thesis_research_pack.yaml`

## Design Outcome

After implementation:

- The default right panel no longer shows a capability grid.
- Idle right panel says, in compact Chinese copy, that the user can describe the paper, experiment, or material in chat.
- Chat Agent decides whether to answer inline, ask one focused question, offer two natural-language paths, or call `launch_feature`.
- When the conversation already contains a topic such as "联邦学习结合大模型微调", asking to start a SCI draft reuses that topic.
- Running missions show a compact stage/status/evidence/review projection.
- Review state outranks progress state when decisions are pending.
- Evidence summary distinguishes found, verified, and used evidence where source data exists.
- Completed missions collapse to summary and next action.
- Follow-up messages such as "继续", "换成综述方向", and "先做 gap" route through Chat Agent with active or selected mission context.

## Task 1: Backend Chat Navigation Contract

Strengthen Chat Agent so it becomes the natural task navigator and stops acting as a pass-through for right-panel button prompts.

- [ ] Add tests in `backend/tests/agents/chat_agent/test_capability_route_cards.py` for prompt contract language:
  - [ ] The rendered capability routing prompt tells the model to reuse recent conversation context.
  - [ ] The prompt allows a compact mission plan before launch when the user asks "你打算怎么做".
  - [ ] The prompt forbids exposing capability ids and route-card internals.
  - [ ] The prompt says right-panel capability cards are not the user interaction model.
- [ ] Add tests in `backend/tests/integration/test_chat_to_feature_launch.py` for chat-first routing:
  - [ ] Prior turn contains "联邦学习结合大模型微调"; next user says "直接开始 SCI 初稿"; the tool call uses `feature_id="research_question_to_paper"` and params include the existing topic.
  - [ ] User asks "联邦学习是什么"; no launch occurs.
  - [ ] User says "联邦学习结合大模型这个方向帮我看看"; response offers natural-language choices and does not expose `research_question_to_paper` or `sci_literature_positioning`.
  - [ ] User says "帮我写 SCI" without topic; response asks exactly one focused question and creates no execution.
- [ ] Update `_build_capability_routing_prompt` in `backend/src/agents/chat_agent/agent.py`:
  - [ ] Add an explicit `reuse_context` rule: use recent user turns, workspace context, uploaded material summaries, and active mission summaries before asking a question.
  - [ ] Add a `mission_plan_then_launch` rule: if the user asks how Wenjin will proceed, give a short editable plan, then launch when the user confirms.
  - [ ] Add a `no_menu_ui` rule: route cards are internal; do not ask the user to click a capability or choose an internal workflow.
  - [ ] Replace example receipts with Chinese copy that says progress will appear in the Mission Console, not a capability panel.
- [ ] Update `backend/src/agents/chat_agent/prompts/system.py`:
  - [ ] Add one base rule that Chat Agent owns task navigation.
  - [ ] Add one base rule that durable work must reuse already supplied research topic/materials.
  - [ ] Keep the existing progressive commitment behavior.
- [ ] Verify that `CapabilitySkillPreloadMiddleware` remains the only route-card loader for Chat Agent. No new route-card fetch path is added.

Acceptance checks:

- [ ] `cd backend && .venv/bin/python -m pytest tests/agents/chat_agent/test_capability_route_cards.py -v`
- [ ] `cd backend && .venv/bin/python -m pytest tests/integration/test_chat_to_feature_launch.py -v`
- [ ] `rg -n "点击.*能力|选择.*能力|capability id|route-card|route_card" backend/src/agents/chat_agent backend/tests/agents/chat_agent backend/tests/integration/test_chat_to_feature_launch.py` shows only internal prompt/tests where exposure is explicitly forbidden.

## Task 2: Research Loop Methodology Contract

Deepen the SCI and thesis harnesses by expressing the research loop in capability methodology, then let TeamKernel consume that existing contract.

- [ ] Update `backend/seed/capabilities/sci/research_question_to_paper.yaml`:
  - [ ] Use a compact stage set mapped to the approved loop: `scope`, `literature_facets`, `reason`, `methodology`, `execute_or_draft`, `analyze`, `synthesize`, `write_review`.
  - [ ] Require artifacts for `research_brief`, `facet_literature_matrix`, `gap_contribution_map`, `methodology_plan`, `claim_inventory`, `claim_evidence_map`, `review_packet`, and manuscript draft outputs.
  - [ ] Put `claim_evidence_alignment`, `review_packet_completeness`, `citation_strength`, and `workflow_trace` on relevant stages or completion gates.
  - [ ] Ensure `claim_policy.mode` remains `two_pass` with extraction and verification artifacts.
  - [ ] Ensure broad-topic literature review instructions ask for 3 to 5 facets before synthesis.
- [ ] Update `backend/seed/capabilities/sci/sci_literature_positioning.yaml`:
  - [ ] Use stages `scope`, `literature_facets`, `gap_reasoning`, `positioning_synthesis`, `review`.
  - [ ] Require `facet_literature_matrix`, `gap_contribution_map`, and `claim_evidence_map`.
  - [ ] Keep this capability positioned as literature/gap work, not full manuscript generation.
- [ ] Update `backend/seed/capabilities/thesis/thesis_research_pack.yaml`:
  - [ ] Use stages `scope`, `literature_facets`, `framework_reasoning`, `outline_methodology`, `synthesize`, `review`.
  - [ ] Require artifacts suitable for thesis students: `research_brief`, `chapter_evidence_map`, `literature_matrix`, `claim_evidence_map`, `next_actions`.
- [ ] Update seed tests in `backend/tests/integration/test_capability_skill_seeds.py`:
  - [ ] Assert the exact stage id sets for the three updated capabilities.
  - [ ] Assert facet literature artifacts exist where expected.
  - [ ] Assert two-pass claim policy remains present for SCI manuscript generation.
- [ ] Update `backend/tests/architecture/test_academic_harness_catalog.py`:
  - [ ] Assert representative SCI/thesis capabilities declare `workflow_trace`, `review_packet_completeness`, and `claim_evidence_alignment`.
  - [ ] Assert broad research capabilities include a facet literature stage.
- [ ] Inspect `backend/src/agents/lead_agent/v2/team/member_context.py`:
  - [ ] Confirm `_methodology_contract` already projects the new stage ids, artifacts, retrieval policy, claim policy, and gates.
  - [ ] Add a targeted test in `backend/tests/agents/lead_agent/v2/test_team_member_context.py` that covers multiple stages with facet artifacts.

Acceptance checks:

- [ ] `cd backend && .venv/bin/python -m pytest tests/integration/test_capability_skill_seeds.py::test_sci_capability_methodology_samples_are_parseable_and_specific -v`
- [ ] `cd backend && .venv/bin/python -m pytest tests/architecture/test_academic_harness_catalog.py -v`
- [ ] `cd backend && .venv/bin/python -m pytest tests/agents/lead_agent/v2/test_team_member_context.py -v`

## Task 3: Mission State Projection

Add a UI-safe mission projection without creating a competing durable state model.

- [ ] In `frontend/lib/execution-run-view.ts`, add projection types:

```ts
export interface RunViewMissionStage {
  id: string;
  label: string;
  status: "pending" | "running" | "completed" | "review" | "blocked";
}

export interface RunViewMissionState {
  title: string;
  goal: string;
  currentStageLabel: string;
  statusLine: string;
  stages: RunViewMissionStage[];
  evidenceSummary: {
    found: number;
    verified: number;
    used: number;
    risky: number;
  };
  reviewSummary: {
    pending: number;
    blockers: number;
    needsConfirmation: number;
  };
  critiqueSummary: {
    status: "not_run" | "pass" | "warning" | "blocked";
    detail: string | null;
  };
  openQuestions: string[];
  nextActions: string[];
}
```

- [ ] Add `mission: RunViewMissionState | null` to `RunView`.
- [ ] Implement `missionStateFromExecution(record, runFacts)` inside `frontend/lib/execution-run-view.ts`:
  - [ ] Derive title and goal from `RunView.title`, task report narrative, execution message, and research state goal.
  - [ ] Derive compact stages from TeamKernel progress items first, then methodology stage hints in runtime state.
  - [ ] Derive evidence counts from `RunViewEvidenceItem`, review packet items, and research state evidence packet.
  - [ ] Derive review counts from `reviewPacket`, `pendingReviewCount`, and quality highlights.
  - [ ] Derive critique status from quality highlights and review-packet blockers.
  - [ ] Derive open questions and next actions from `ResearchStateV1` located in runtime or result payloads.
  - [ ] Limit visible arrays to small bounded counts: up to 5 stages, 3 open questions, and 3 next actions.
- [ ] Add helper readers in `execution-run-view.ts` for `ResearchStateV1`-shaped objects:
  - [ ] `researchStateFromRuntimeState`
  - [ ] `researchStateFromTaskReport`
  - [ ] `missionStageLabel`
  - [ ] `evidenceVerificationCounts`
- [ ] Keep all raw object access in `execution-run-view.ts`. React components must consume `RunView.mission`.
- [ ] Add tests in `frontend/tests/unit/lib/execution-run-view.test.ts`:
  - [ ] Active TeamKernel record projects a mission with human stage labels.
  - [ ] Review-packet blockers make `critiqueSummary.status === "blocked"`.
  - [ ] Research state open questions and next actions are bounded and visible.
  - [ ] Evidence count separates used review-packet evidence from merely found node evidence when source data contains enough detail.
  - [ ] Projection returns `null` only when there is no selected execution and no mission-worthy state.

Acceptance checks:

- [ ] `cd frontend && npx vitest run tests/unit/lib/execution-run-view.test.ts`
- [ ] `cd frontend && npm run typecheck`

## Task 4: Remove Default Right-Panel Capability Launcher

Convert `LiveWorkflowPanel` and `OverviewView` from a capability launcher into a Mission Console.

- [ ] Update `frontend/app/(workbench)/workspaces/[id]/page.tsx`:
  - [ ] Stop passing `features` into `LiveWorkflowPanel`.
  - [ ] Keep `features` loading for `ChatPanel` thread-entry seed resolution only.
  - [ ] Add or update a test proving `ChatPanel` does not render a feature menu from the `features` prop.
- [ ] Update `frontend/app/(workbench)/workspaces/[id]/components/LiveWorkflowPanel.tsx`:
  - [ ] Remove `WorkspaceCapability` import.
  - [ ] Remove `features` prop from `LiveWorkflowPanelProps`.
  - [ ] Remove `handleLaunchFeature`.
  - [ ] Remove `isSuperWorkflowCapability` from this file.
  - [ ] Keep `handleApproveIntakeSpec`, because accepted specs still route through chat metadata and Chat Agent orchestration.
  - [ ] Pass mission projection data from the selected run view or view model into `OverviewView`.
- [ ] Update `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/useLiveWorkflowViewModel.ts`:
  - [ ] Add `selectedRunView` or `mission` to `LiveWorkflowViewModel` so components do not re-project the same execution.
  - [ ] Keep `resolveAutoWorkbenchTab` priority as review first, active run second, evidence third, overview idle last.
  - [ ] Add `hasMissionActivity` as a derived boolean from selected record, running record, review count, evidence count, or mission.
- [ ] Replace `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/OverviewView.tsx`:
  - [ ] Props become mission/activity props, records, counts, and `onOpenRun`.
  - [ ] Remove `WorkspaceCapability` import.
  - [ ] Remove feature grid rendering.
  - [ ] Idle copy: `还没有正在执行的研究任务。直接在左侧描述你想推进的论文、实验或材料。`
  - [ ] Show compact actions for history/evidence only when backing state exists.
  - [ ] When a mission exists, show mission title, status line, stage markers, evidence summary, review summary, and next action.
  - [ ] Keep recent runs list but reduce it to the latest 3 to 4 rows.
- [ ] Update `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/styles.ts`:
  - [ ] Delete `featureGrid`, `featureButton`, `featureTitle`, `featureDescription`, `featureMetaHint`, and `featureGuidance`.
  - [ ] Add compact Mission Console styles using `--wjn-*` only.
  - [ ] Keep border radius at or below existing system radius.
  - [ ] Avoid nested card styling.
- [ ] Update tests in `frontend/tests/unit/v2/LiveWorkflowPanel.test.tsx`:
  - [ ] Idle panel does not render capability names or feature buttons.
  - [ ] Idle panel renders the chat-first empty state copy.
  - [ ] Clicking right-panel overview cannot send a capability launch prompt.
  - [ ] Active run shows progress or mission state.
  - [ ] Pending review makes review visible and prioritized.
- [ ] Update tests in `frontend/tests/unit/v2/live-workflow-view-model.test.ts`:
  - [ ] `hasMissionActivity` is false for no records.
  - [ ] `hasMissionActivity` is true for active run, pending review, evidence, or selected completed mission.
  - [ ] Auto tab stays `review` when review is pending, even if a completed run also has evidence.

Acceptance checks:

- [ ] `cd frontend && npx vitest run tests/unit/v2/LiveWorkflowPanel.test.tsx tests/unit/v2/live-workflow-view-model.test.ts`
- [ ] `cd frontend && npm run typecheck`
- [ ] `rg -n "handleLaunchFeature|featureGrid|featureButton|能力入口|先确认信息，再进入团队任务" frontend/app frontend/tests` returns no default workspace UI references.

## Task 5: Simplify Mission Console Header and Layout

Make the right panel feel like a compact mission/status surface, not a dense dashboard.

- [ ] Update `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/WorkbenchHeader.tsx`:
  - [ ] Change title from "研究工作台" to "研究任务" or active mission title when provided.
  - [ ] Keep the eyebrow only when it adds useful workspace context.
  - [ ] Show Review tab only when review count is positive or user is already on review.
  - [ ] Show Evidence tab only when evidence count is positive or user is already on evidence.
  - [ ] Show Progress tab only when there is an active or selected run.
  - [ ] Show History through the existing secondary action when there are records but no active run.
  - [ ] Keep fullscreen and intervention controls.
- [ ] Update `frontend/stores/workbench-layout-store.ts`:
  - [ ] Use a desktop split that gives chat more space by default.
  - [ ] Keep min/max bounds so review-heavy states can still expand.
  - [ ] Do not store mission content in this store.
- [ ] Update `frontend/app/(workbench)/workspaces/[id]/page.tsx`:
  - [ ] If there is no mission activity and not fullscreen, render the right side in a visually quiet width or compact state using existing layout state.
  - [ ] Preserve keyboard resizer behavior.
  - [ ] Preserve mobile surface tabs, with chat remaining the first surface.
- [ ] Add or update tests:
  - [ ] Header hides evidence tab when evidence count is zero.
  - [ ] Header hides review tab when review count is zero and active tab is not review.
  - [ ] Header keeps fullscreen accessible.
  - [ ] Workbench split still exposes the separator on desktop.

Acceptance checks:

- [ ] `cd frontend && npx vitest run tests/unit/v2/LiveWorkflowPanel.test.tsx`
- [ ] `cd frontend && npm run typecheck`
- [ ] Manual browser check at `http://localhost:2026/workspaces/<workspace-id>` for idle, active, review, and mobile widths.

## Task 6: Review, Evidence, and Follow-Up UX

Tighten the user-facing review/evidence language and ensure intervention/follow-up remains chat-first.

- [ ] Update `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/ReviewView.tsx`:
  - [ ] Ensure high-risk evidence/citation/claim/document items are visually distinct and unchecked by default through existing ChangeSet projection.
  - [ ] Ensure bulk accept remains disabled when high-risk or blocker units exist.
  - [ ] Ensure empty review state uses concise Chinese copy.
- [ ] Update `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/EvidenceView.tsx`:
  - [ ] Show default summary before detailed evidence rows.
  - [ ] Use found/verified/used wording when `RunView.mission.evidenceSummary` is available.
  - [ ] Keep raw stdout, raw JSON, and internal refs out of the default view.
- [ ] Update `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/InterventionBar.tsx`:
  - [ ] Copy should say the instruction is sent back through chat orchestration.
  - [ ] It must not claim direct mutation of TeamKernel internals.
- [ ] Update the intervention prompt in `LiveWorkflowPanel.tsx`:
  - [ ] Use natural wording such as "请基于当前任务继续处理" and pass execution id in metadata.
  - [ ] Keep the existing cancel-at-safe-point behavior.
  - [ ] Do not send a capability id from the right panel.
- [ ] Add tests:
  - [ ] EvidenceView renders found/verified/used summary for projected mission state.
  - [ ] ReviewView keeps blocked/high-risk review items out of bulk accept.
  - [ ] Intervention sends a chat message with natural instruction metadata, not a direct feature launch.

Acceptance checks:

- [ ] `cd frontend && npx vitest run tests/unit/v2/LiveWorkflowPanel.test.tsx`
- [ ] `cd frontend && npm run typecheck`

## Task 7: Backend Mission Context for Follow-Up

Give Chat Agent bounded mission context so follow-up turns do not cold-start.

- [ ] Inspect existing middleware context injected into `ThreadState`:
  - [ ] `ExecutionMiddleware`
  - [ ] `ThreadDataMiddleware`
  - [ ] `WorkspaceContextMiddleware`
  - [ ] `CapabilitySkillPreloadMiddleware`
- [ ] Add or update a bounded active/selected mission context block:
  - [ ] Source it from latest active execution and selected execution summaries.
  - [ ] Include execution id, title, goal, status, current stage, open questions, next actions, pending review count, evidence count, and capability display name.
  - [ ] Keep the block under a fixed character limit.
  - [ ] Store it in Chat Agent prompt state, not a new table.
- [ ] Update `backend/src/agents/chat_agent/agent.py` prompt assembly:
  - [ ] Render mission context before capability route cards.
  - [ ] Tell the model that "继续" should prefer the active mission when it is unambiguous.
  - [ ] Tell the model to ask one question when "继续" could mean multiple selected/completed missions.
- [ ] Add tests in `backend/tests/integration/test_chat_to_feature_launch.py` or a focused middleware test:
  - [ ] Active mission context is included in the prompt.
  - [ ] Follow-up "继续深化方法部分" can launch or continue with the active execution context.
  - [ ] Missing active mission context does not fabricate one.

Acceptance checks:

- [ ] `cd backend && .venv/bin/python -m pytest tests/integration/test_chat_to_feature_launch.py -v`
- [ ] `cd backend && .venv/bin/python -m pytest tests/agents/chat_agent/test_capability_route_cards.py -v`

## Task 8: Cleanup and Architecture Convergence

Remove stale UI paths and lock in the new boundary.

- [ ] Remove unused imports and props after Tasks 4 through 7:
  - [ ] `WorkspaceCapability` from right-panel files.
  - [ ] `isSuperWorkflowCapability` from `LiveWorkflowPanel.tsx`.
  - [ ] Feature-grid styles from `styles.ts`.
  - [ ] Tests that assert right-panel launch behavior.
- [ ] Run text scans:
  - [ ] `rg -n "handleLaunchFeature|featureGrid|featureButton|能力入口|选择一个方向后|先确认信息，再进入团队任务" frontend/app frontend/tests`
  - [ ] `rg -n "--v2-" frontend/app/'(workbench)' frontend/lib frontend/stores`
  - [ ] `rg -n "raw log|raw JSON|tool JSON|capability id" frontend/app/'(workbench)' backend/src/agents/chat_agent`
- [ ] Update docs:
  - [ ] `docs/current/wenjin-research-navigation-uiux.md` reflects chat-first Mission Console.
  - [ ] `docs/current/frontend-mission-contract.md` states Mission policies are backend contracts, not default right-panel buttons.
  - [ ] `docs/current/workspace-current-state.md` describes follow-up routing through Chat Agent with mission context.
- [ ] Keep docs concise. Do not document the removed button launcher as a supported alternate mode.

Acceptance checks:

- [ ] Text scans show no default right-panel launcher references.
- [ ] Docs describe one architecture path: Chat Agent owns task navigation; Mission Console projects execution state.

## Release Verification

Run these commands before marking implementation complete:

- [ ] `cd backend && .venv/bin/python -m pytest tests/agents/chat_agent/test_capability_route_cards.py -v`
- [ ] `cd backend && .venv/bin/python -m pytest tests/integration/test_chat_to_feature_launch.py -v`
- [ ] `cd backend && .venv/bin/python -m pytest tests/integration/test_capability_skill_seeds.py::test_sci_capability_methodology_samples_are_parseable_and_specific -v`
- [ ] `cd backend && .venv/bin/python -m pytest tests/architecture/test_academic_harness_catalog.py -v`
- [ ] `cd backend && .venv/bin/python -m pytest tests/agents/lead_agent/v2/test_team_member_context.py -v`
- [ ] `cd frontend && npx vitest run tests/unit/lib/execution-run-view.test.ts`
- [ ] `cd frontend && npx vitest run tests/unit/v2/LiveWorkflowPanel.test.tsx tests/unit/v2/live-workflow-view-model.test.ts`
- [ ] `cd frontend && npm run typecheck`
- [ ] `cd frontend && npm run build`

Manual browser verification:

- [ ] Start the stack or frontend dev server.
- [ ] Open a SCI workspace.
- [ ] Confirm idle right side has no capability grid.
- [ ] Ask a lightweight concept question and confirm no run starts.
- [ ] Ask "我想写一篇联邦学习结合大模型微调的 SCI" and confirm Chat Agent launches only after enough context.
- [ ] Confirm Mission Console opens with compact mission status.
- [ ] Confirm pending review moves the console to review.
- [ ] Confirm evidence view shows a summary before detail.
- [ ] Confirm "继续深化方法部分" reuses the active or selected mission context.
- [ ] Confirm mobile keeps chat as the primary surface.

## Commit Plan

- [ ] Commit 1: backend chat navigation prompt and tests.
- [ ] Commit 2: capability methodology seed hardening and seed/catalog tests.
- [ ] Commit 3: `RunView` mission projection and frontend projection tests.
- [ ] Commit 4: Mission Console UI replacing capability grid and related tests.
- [ ] Commit 5: header/layout/review/evidence/follow-up polish and docs.

Each commit must keep the repository typecheckable and targeted tests passing for the files touched in that commit.

## Hand-Off Notes

- Use subagent-driven implementation for independent backend prompt tests, capability seed updates, frontend projection, and UI rewrite work.
- The highest-risk implementation boundary is Task 4 because it removes a user-visible launch path. Keep the deletion deliberate and verify the chat launch path still works.
- The second highest-risk boundary is Task 7 because mission context must remain bounded and derived from existing execution state.
- Do not preserve the removed capability grid behind a feature flag. Admin/catalog editing can keep capability display metadata, but default workspace UX should not render it.
