# SCI Citation Library Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make SCI literature search, Library source storage, manuscript citation usage, `refs.bib` projection, Prism review, and LaTeX compile behave as one closed citation system.

**Architecture:** Capability YAML declares an explicit `citation_policy`; LeadAgentRuntime turns that policy into runtime context, syncs Library sources into Prism `refs.bib`, validates staged manuscript citations, and records citation usage/provenance. Skills remain review-only, but their prompts must treat Library Source citation keys as the only allowed citation surface.

**Tech Stack:** Python 3.13, Pydantic v2, FastAPI/DataService client, LangGraph Lead Agent v2, YAML seed capabilities/skills, pytest, Next.js browser E2E through local Docker.

---

### Task 1: Citation Policy Schema

**Files:**
- Modify: `backend/src/services/capability_schema.py`
- Modify: `backend/tests/services/test_capability_schema.py`
- Modify: `backend/seed/capabilities/sci/sci_literature_positioning.yaml`
- Modify: `backend/seed/capabilities/sci/research_question_to_paper.yaml`

- [ ] **Step 1: Write the failing schema test**

Add a test proving `citation_policy` is accepted by `CapabilityV2YamlModel`, serialized into `definition_json`, and rejects invalid values.

- [ ] **Step 2: Run the schema test and verify RED**

Run: `cd backend && .venv/bin/python -m pytest tests/services/test_capability_schema.py::TestCapabilityV2Yaml::test_citation_policy_round_trips_to_catalog_data -q`

Expected: fail because `citation_policy` is currently an extra field.

- [ ] **Step 3: Implement the minimal schema**

Add a focused `CapabilityV2CitationPolicyModel` with source scope, allowed citation command, bibliography projection file, missing-key behavior, and usage-recording toggle.

- [ ] **Step 4: Run the schema test and verify GREEN**

Run the same test and confirm it passes.

### Task 2: Runtime Citation Context And Usage

**Files:**
- Modify: `backend/src/agents/lead_agent/v2/runtime.py`
- Modify: `backend/tests/agents/lead_agent/v2/test_runtime.py`

- [ ] **Step 1: Write failing runtime tests**

Add tests that prove:
- `citation_policy` enables Library context loading even when `room_reads.library` is missing.
- staged `main.tex` citations are validated against Library citation keys before Prism review.
- staged `main.tex` citation keys are recorded through DataService citation usage.

- [ ] **Step 2: Run targeted tests and verify RED**

Run: `cd backend && .venv/bin/python -m pytest tests/agents/lead_agent/v2/test_runtime.py::<new-test-name> -q`

Expected: fail because runtime currently only checks `context_policy.room_reads.library` and does not record citation usage from staged Prism content.

- [ ] **Step 3: Implement runtime policy enforcement**

Extend `_capability_policy`, `_needs_library_context`, `_stage_prism_review_items`, and helpers so policy-aware capabilities load Library context, ensure `refs.bib`, validate `\cite{}` keys, and record source usage for staged manuscript content.

- [ ] **Step 4: Run targeted runtime tests and verify GREEN**

Run the new runtime tests and existing Prism staging tests.

### Task 3: Skill And Capability Prompt Closure

**Files:**
- Modify: `backend/seed/skills/research-scout.yaml`
- Modify: `backend/seed/skills/literature-synthesizer.yaml`
- Modify: `backend/seed/skills/manuscript-architect.yaml`
- Modify: `backend/seed/skills/manuscript-writer.yaml`
- Modify: `backend/seed/skills/citation-auditor.yaml`
- Modify: `backend/seed/capabilities/sci/sci_literature_positioning.yaml`
- Modify: `backend/seed/capabilities/sci/research_question_to_paper.yaml`
- Modify: `docs/current/workspace-reference-library.md`

- [ ] **Step 1: Update seed prompts**

Make the prompts explicit: literature positioning produces Library-ready source records and citation-ready plans; manuscript writing uses only Library citation keys; citation audit blocks missing keys.

- [ ] **Step 2: Update docs**

Document `citation_policy` and the runtime invariant that `refs.bib` is a projection from Source DataService, not an agent-authored file.

### Task 4: Verification And Browser E2E

**Files:**
- No new source files.

- [ ] **Step 1: Run backend target tests**

Run schema/runtime/reference/prism/latex target tests.

- [ ] **Step 2: Rebuild local services**

Run local Docker build for gateway, worker, memory-worker, frontend, nginx.

- [ ] **Step 3: Browser E2E**

Create or reuse an SCI workspace and verify:
- literature positioning imports real/curated sources into Library;
- paper writing uses Library citation keys in `main.tex`;
- `refs.bib` appears in Prism resources;
- citations validate against `refs.bib`;
- Prism apply and LaTeX compile complete without missing citation failures.

