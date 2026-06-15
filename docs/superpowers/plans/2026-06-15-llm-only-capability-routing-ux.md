# LLM-only Capability Routing UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Add LLM-only capability routing guidance so Chat Agent can flexibly answer, clarify, offer choices, or launch workspace capabilities without embedding infrastructure.

**Architecture:** DataService capability catalog remains the source of truth. `capability.v2` gains an optional `routing` object, catalog projections preserve it, Chat Agent renders compact route cards and applies a UX-aware routing rubric, and route/UX tests guard against false launches and rigid clarification.

**Tech Stack:** Python 3.13, Pydantic v2, FastAPI/DataService catalog, pytest, YAML capability seeds.

---

## Files

- Modify: `backend/src/services/capability_schema.py`
- Modify: `backend/src/dataservice/domains/catalog/contracts.py`
- Modify: `backend/src/dataservice/domains/catalog/projection.py`
- Modify: `backend/src/agents/chat_agent/agent.py`
- Modify: `backend/src/agents/chat_agent/prompts/system.py`
- Modify: `backend/seed/capabilities/**.yaml`
- Create: `backend/tests/agents/chat_agent/test_capability_route_cards.py`
- Modify: `backend/tests/services/test_capability_schema.py`
- Modify: `backend/tests/dataservice/test_catalog_domain.py`
- Modify: `backend/tests/seed/test_capability_seeds_load.py`
- Create: `backend/tests/agents/chat_agent/test_capability_routing_eval.py`
- Modify: `docs/current/workspace-feature-catalog.md`
- Modify: `docs/current/architecture.md`
- Modify: `docs/current/frontend-feature-plugin-contract.md`
- Modify: `docs/current/release-gate-checklist.md`

## Task 1: Add `capability.v2.routing` Schema

**Files:**
- Modify: `backend/src/services/capability_schema.py`
- Test: `backend/tests/services/test_capability_schema.py`

- [x] **Step 1: Write failing schema tests**

Add tests that prove a capability seed can include `routing`, rejects unknown routing keys, and exports routing through `to_catalog_data()`:

```python
def test_capability_v2_accepts_routing_contract():
    model = CapabilityV2YamlModel(**_valid_capability_payload(routing={
        "when_to_use": ["用户需要整理文献、gap 和创新点"],
        "not_for": ["概念解释"],
        "user_intents": ["找研究空白"],
        "positive_examples": ["联邦学习结合大模型有什么创新点？"],
        "negative_examples": ["联邦学习是什么？"],
        "minimum_context": {"goal_or_topic": "required"},
        "ambiguity": {
            "overlaps_with": ["research_question_to_paper"],
            "ask_user_when": ["同时像文献定位和完整写作"],
        },
        "clarification": {
            "ask_when_missing": {"goal_or_topic": "你想聚焦哪个具体主题？"},
            "choice_when_ambiguous": {
                "research_vs_writing": {
                    "question": "你想先找研究空白，还是直接写初稿？",
                    "options": [
                        {"label": "先找研究空白", "capability_id": "sci_literature_positioning"},
                        {"label": "直接写初稿", "capability_id": "research_question_to_paper"},
                    ],
                }
            },
        },
        "user_guidance": {
            "launch_intro": "我会让文献专家先整理相关工作、gap 和可用论断。",
            "lightweight_answer_hint": "这个问题我可以先直接解释，不需要启动团队任务。",
        },
    }))

    catalog = model.to_catalog_data()

    assert catalog["routing"]["minimum_context"]["goal_or_topic"] == "required"
```

- [x] **Step 2: Run test and verify RED**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/services/test_capability_schema.py -q
```

Expected: fails because `routing` is not allowed by `CapabilityV2YamlModel`.

- [x] **Step 3: Implement routing schema models**

Add focused Pydantic models:

- `CapabilityV2RoutingOptionModel`
- `CapabilityV2RoutingChoiceModel`
- `CapabilityV2RoutingClarificationModel`
- `CapabilityV2RoutingGuidanceModel`
- `CapabilityV2RoutingModel`

Add `routing: CapabilityV2RoutingModel = Field(default_factory=CapabilityV2RoutingModel)` to `CapabilityV2YamlModel`.

- [x] **Step 4: Run schema tests and verify GREEN**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/services/test_capability_schema.py -q
```

Expected: passes.

## Task 2: Preserve Routing Through DataService Catalog Projection

**Files:**
- Modify: `backend/src/dataservice/domains/catalog/contracts.py`
- Modify: `backend/src/dataservice/domains/catalog/projection.py`
- Modify: `backend/tests/dataservice/test_catalog_domain.py`

- [x] **Step 1: Write failing catalog projection test**

Add a test that upserts a capability with `routing` and asserts the returned record includes `routing`.

```python
assert record.routing["when_to_use"] == ["用户需要整理文献、gap 和创新点"]
assert record.definition_json["routing"]["user_intents"] == ["找研究空白"]
```

- [x] **Step 2: Run test and verify RED**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/dataservice/test_catalog_domain.py -q
```

Expected: fails because `CapabilityDefinitionRecord` has no `routing` field.

- [x] **Step 3: Implement projection**

Add `routing: dict[str, Any] = Field(default_factory=dict)` to `CapabilityDefinitionRecord`.

In `capability_to_record()`, set:

```python
definition_json = dict(getattr(capability, "definition_json", None) or {})
routing = definition_json.get("routing") if isinstance(definition_json.get("routing"), dict) else {}
```

Pass `routing=dict(routing)` into the record.

- [x] **Step 4: Run catalog tests and verify GREEN**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/dataservice/test_catalog_domain.py -q
```

Expected: passes.

## Task 3: Render Compact Route Cards in Chat Agent Prompt

**Files:**
- Modify: `backend/src/agents/chat_agent/agent.py`
- Create: `backend/tests/agents/chat_agent/test_capability_route_cards.py`

- [x] **Step 1: Write failing route card tests**

Create tests for `_render_workspace_available_skills()`:

- route cards include `when`, `not_for`, `minimum_context`, `launch_intro`;
- hidden capabilities are not rendered;
- route cards do not include full graph templates or raw YAML;
- legacy `<capability ... triggers=...>` format is replaced by `<capability_route_card ...>`.

- [x] **Step 2: Run tests and verify RED**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/agents/chat_agent/test_capability_route_cards.py -q
```

Expected: fails because route-card rendering is not implemented.

- [x] **Step 3: Implement bounded route card renderer**

Add helpers in `agent.py`:

- `_route_text_list(value, limit=3, max_chars=160) -> str`
- `_route_minimum_context(routing: dict[str, Any]) -> str`
- `_render_capability_route_card(capability: dict[str, Any]) -> str`

Update `_render_workspace_available_skills()` to render `<capability_route_card />` rows and skip hidden tier capabilities.

- [x] **Step 4: Run route card tests and verify GREEN**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/agents/chat_agent/test_capability_route_cards.py -q
```

Expected: passes.

## Task 4: Add UX-aware Routing Rubric to Chat Agent Prompt

**Files:**
- Modify: `backend/src/agents/chat_agent/agent.py`
- Modify: `backend/src/agents/chat_agent/prompts/system.py`
- Modify: `backend/tests/agents/chat_agent/test_prompts_snapshot.py`
- Create: `backend/tests/agents/chat_agent/test_capability_routing_eval.py`

- [x] **Step 1: Write failing prompt tests**

Assert prompt contains the four decision modes:

- `answer_in_chat`
- `ask_clarification`
- `offer_choices`
- `launch_feature`

Assert prompt forbids exposing internal route terms to users.

- [x] **Step 2: Write route/UX eval tests**

Create deterministic tests that inspect the rendered prompt and mocked catalog route cards for cases like:

- `联邦学习结合大模型有什么创新点？` should have enough guidance to launch literature positioning.
- `联邦学习是什么？` should be covered by direct-chat guidance.
- `帮我写SCI` should be covered by one-question clarification guidance.
- ambiguous wording should be covered by two-choice guidance.

These tests should not call a real LLM.

- [x] **Step 3: Run tests and verify RED**

Run:

```bash
cd backend
.venv/bin/python -m pytest \
  tests/agents/chat_agent/test_prompts_snapshot.py \
  tests/agents/chat_agent/test_capability_routing_eval.py -q
```

Expected: fails because rubric text and route eval fixtures are absent.

- [x] **Step 4: Implement prompt rubric**

Update `_build_capability_skill_prompt()` and base system prompt to explain:

- direct answer for lightweight questions;
- ask one question for missing minimum context;
- offer two natural choices for ambiguity;
- call `launch_feature` only when clear and sufficiently contextualized;
- never expose capability ids, schema, confidence, route-card internals, or trigger phrases.

- [x] **Step 5: Run prompt tests and verify GREEN**

Run:

```bash
cd backend
.venv/bin/python -m pytest \
  tests/agents/chat_agent/test_prompts_snapshot.py \
  tests/agents/chat_agent/test_capability_routing_eval.py -q
```

Expected: passes.

## Task 5: Add Routing Blocks to Capability Seeds

**Files:**
- Modify: `backend/seed/capabilities/**.yaml`
- Modify: `backend/tests/seed/test_capability_seeds_load.py`

- [x] **Step 1: Write failing seed coverage test**

Assert every enabled, non-hidden `capability.v2` seed has a non-empty `routing.when_to_use` and `routing.minimum_context`.

- [x] **Step 2: Run test and verify RED**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/seed/test_capability_seeds_load.py -q
```

Expected: fails because seeds do not yet include routing blocks.

- [x] **Step 3: Add routing blocks to visible seeds**

Add concise routing blocks for all enabled, user-visible capabilities across:

- thesis
- sci
- proposal
- software_copyright
- patent

Keep text short. Do not duplicate `team_policy` or graph details.

- [x] **Step 4: Run seed tests and verify GREEN**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/seed/test_capability_seeds_load.py -q
```

Expected: passes.

## Task 6: Update Current Docs and Release Gate

**Files:**
- Modify: `docs/current/workspace-feature-catalog.md`
- Modify: `docs/current/architecture.md`
- Modify: `docs/current/frontend-feature-plugin-contract.md`
- Modify: `docs/current/release-gate-checklist.md`

- [x] **Step 1: Update docs**

Document:

- routing is LLM-only and non-embedding;
- route cards are catalog projections;
- Chat Agent owns entry routing;
- Lead Agent owns post-launch execution;
- user-facing chat must not expose routing internals;
- release gate requires routing blocks for visible primary capabilities.

- [x] **Step 2: Verify docs do not contradict architecture**

Run:

```bash
rg -n "embedding|vector|router service|confidence|fallback" docs/current docs/superpowers/specs/2026-06-15-llm-only-capability-routing-ux-design.md
```

Expected: only allowed mentions such as "No embedding" or "not expose confidence".

## Task 7: Full Verification and Review

**Files:**
- All modified files.

- [x] **Step 1: Run focused backend tests**

Run:

```bash
cd backend
.venv/bin/python -m pytest \
  tests/services/test_capability_schema.py \
  tests/dataservice/test_catalog_domain.py \
  tests/agents/chat_agent/test_capability_route_cards.py \
  tests/agents/chat_agent/test_capability_routing_eval.py \
  tests/agents/chat_agent/test_prompts_snapshot.py \
  tests/seed/test_capability_seeds_load.py -q
```

Expected: passes.

- [x] **Step 2: Run backend lint**

Run:

```bash
cd backend
.venv/bin/python -m ruff check src tests
```

Expected: passes.

- [x] **Step 3: Run full backend test suite if focused checks pass**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/ -q
```

Expected: passes.

- [x] **Step 4: Review diff**

Run:

```bash
git diff --check
git diff --stat
git diff -- backend/src/agents/chat_agent/agent.py backend/src/services/capability_schema.py
```

Confirm:

- no execution bypass;
- no embedding or vector dependencies;
- no frontend router UI;
- route cards are bounded;
- user-facing copy avoids internals.

- [x] **Step 5: Commit**

Commit after verification:

```bash
git add backend docs
git commit -m "feat: add llm capability routing guidance"
```
