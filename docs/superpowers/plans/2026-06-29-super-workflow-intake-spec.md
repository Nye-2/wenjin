# Super Workflow Intake Spec Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make software copyright and math modeling capabilities start with an agent-written Markdown clarification spec, then let the user approve the spec from the right workbench panel so execution still goes through the existing chat-agent `launch_feature` path.

**Architecture:** Reuse the current two-agent topology. Chat Agent drafts an `IntakeSpecV1` through a builtin tool and returns it as an ordinary `tool_result` block. The frontend recognizes that result, shows a compact chat card, stores the active spec in the workbench layout store, and renders a Markdown preview tab in `LiveWorkflowPanel`. Approval sends a new chat message with `orchestration.feature_id` and `orchestration.params`, so the existing auto-launch middleware and Lead Agent pipeline remain the only execution path.

**Tech Stack:** FastAPI/LangChain tools/Pydantic v2 on backend; Next.js/React/Zustand on frontend; existing Vitest/Pytest suites for coverage.

---

- [x] Add backend `IntakeSpecV1` contract and `draft_intake_spec` builtin tool.
- [x] Update Chat Agent routing/tool registration so super workflows draft specs before launch.
- [x] Protect runtime auto-launch extraction so `workbench_launch.mode=intake` never starts Lead Agent directly.
- [x] Add frontend intake spec parser/helper with unit coverage.
- [x] Render intake spec chat cards from `tool_result` blocks.
- [x] Add right-side Markdown spec preview tab and approve-to-launch action.
- [x] Change super workflow capability buttons to enter intake mode instead of direct launch.
- [x] Run targeted backend/frontend verification and fix regressions.
