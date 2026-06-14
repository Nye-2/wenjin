# Admin Control Plane SSOT Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Converge the admin-managed model, pricing, and credit control plane around DataService as SSOT, starting with the runtime pricing-policy binding and admin model configuration safety path.

**Architecture:** DataService remains the authoritative owner of model catalog, pricing policies, credit operations, and catalog records. Gateway exposes admin-safe projections and refreshes runtime caches. Runtime caches are read-only projections that must preserve billing metadata such as `pricing_policy_id` without leaking secrets.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy async, Pydantic v2, pytest, Next.js 16, React 19, TypeScript, Zustand.

---

### Task 1: Runtime Model Pricing Policy Binding

**Files:**
- Modify: `backend/src/services/model_catalog_cache.py`
- Test: `backend/tests/services/test_model_catalog_cache.py`
- Test: `backend/tests/services/test_credit_service.py`

- [ ] **Step 1: Add failing cache test**

Add an assertion that a runtime model payload with `pricing_policy_id` keeps that value after `install_model_catalog_snapshot`.

- [ ] **Step 2: Run cache test and verify failure**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/services/test_model_catalog_cache.py -q
```

Expected before implementation: failure because `RuntimeModelConfig` has no `pricing_policy_id`.

- [ ] **Step 3: Implement cache field**

Add `pricing_policy_id: str | None` to `RuntimeModelConfig`, populate it in `_to_runtime_config`, and include it in `safe_dict`.

- [ ] **Step 4: Add credit-service resolution test**

Add a test proving `CreditService` resolves model-specific policy through runtime catalog `pricing_policy_id` before falling back to first enabled `model_usage`.

- [ ] **Step 5: Run targeted backend tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/services/test_model_catalog_cache.py tests/services/test_credit_service.py -q
```

Expected: all selected tests pass.

### Task 2: Admin Model Form Pricing and Headers UX

**Files:**
- Modify: `frontend/app/dashboard/admin/models/ModelDialog.tsx`
- Modify: `frontend/app/dashboard/admin/models/page.tsx`
- Modify: `frontend/lib/api/admin-pricing.ts`
- Test: add or update frontend unit tests if an existing admin model test harness exists.

- [ ] **Step 1: Inspect existing frontend test harness**

Search for admin model tests. If none exist, keep this as typed UI implementation and rely on `npm run typecheck` plus browser smoke test.

- [ ] **Step 2: Load model usage pricing policies**

In `ModelDialog`, fetch enabled `model_usage` policies when the dialog opens and replace the free-text pricing policy input with a select that supports "unbound" and each policy key.

- [ ] **Step 3: Add structured headers editor**

Represent `default_headers` as editable key/value rows. Preserve redacted values only as display state; do not submit `[redacted]` as a real header value.

- [ ] **Step 4: Keep API key write-only semantics**

Retain "leave blank to keep existing key" behavior for edits. Make the placeholder explicit and ensure update payload omits blank keys.

- [ ] **Step 5: Run frontend checks**

Run:

```bash
cd frontend && npm run typecheck
cd frontend && npx vitest run
```

Expected: typecheck and tests pass.

### Task 3: Admin Pricing Policy Form Guardrails

**Files:**
- Modify: `frontend/app/dashboard/admin/credits/pricing/PricingPolicyDialog.tsx`
- Modify: `frontend/app/dashboard/admin/credits/pricing/PricingSimulator.tsx`

- [ ] **Step 1: Normalize default sandbox policy shape**

Ensure the frontend default sandbox config matches backend `SandboxPricingPolicyConfig` expectations: operation, default tier, minimum billable seconds, startup fee, credits per minute, and max charge.

- [ ] **Step 2: Improve model usage config defaults**

Expose raw cost fields and cached/reasoning weights in the default JSON so admin-created model policies do not accidentally omit important model-specific cost controls.

- [ ] **Step 3: Run frontend checks**

Run:

```bash
cd frontend && npm run typecheck
cd frontend && npx vitest run
```

Expected: typecheck and tests pass.

### Task 4: Release Gate and Documentation Alignment

**Files:**
- Modify: `docs/current/environment-variables.md`
- Modify: `docs/current/release-gate-checklist.md`
- Modify: `docs/current/architecture.md`
- Test: `backend/tests/quality/test_model_catalog_pricing_gate.py`

- [ ] **Step 1: Review current docs against SSOT spec**

Update docs to state that admin-managed model catalog and pricing policies live in DataService and that env model configuration is bootstrap/development only.

- [ ] **Step 2: Run release-gate tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/quality/test_model_catalog_pricing_gate.py -q
```

Expected: tests pass.

### Task 5: Browser Smoke Test

**Files:**
- No production file required unless smoke test reveals a bug.

- [ ] **Step 1: Start local stack or dev servers**

Use the existing project start flow. If a server is already running, reuse it.

- [ ] **Step 2: Exercise admin paths**

In browser, verify:

- admin model list loads;
- model dialog opens;
- pricing policy selector is present;
- API key field is write-only;
- default headers editor is present;
- pricing policy page loads;
- credit center pages still load.

- [ ] **Step 3: Fix any discovered bug with TDD when practical**

If a backend behavior bug is found, write a failing test first. If a pure UI layout bug has no existing harness, verify through typecheck and browser.
