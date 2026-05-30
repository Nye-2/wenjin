# Admin Model Catalog Credit Pricing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the DataService-backed admin model catalog, encrypted model API keys, admin-managed pricing policies, and credit reservation/settlement foundation from `docs/superpowers/specs/2026-05-30-admin-model-catalog-and-credit-pricing-design.md`.

**Architecture:** DataService owns model catalog, pricing policy, and reservation persistence. Gateway exposes admin/user APIs and runtime services use a cached model resolver snapshot. Credit settlement moves from fixed `tokens_per_credit` to policy-driven value pricing while keeping user-facing displays credit-only.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy async, Alembic, Pydantic v2, LangChain `ChatOpenAI`, Next.js 16, React 19, TypeScript, Zustand/admin dashboard patterns.

---

## Current Baseline

Worktree: `/Users/ze/wenjin/.worktrees/admin-model-catalog-pricing`

Branch: `codex/admin-model-catalog-pricing`

Baseline already verified before writing this plan:

```bash
cd /Users/ze/wenjin/.worktrees/admin-model-catalog-pricing/backend
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy -u NO_PROXY -u no_proxy \
  .venv/bin/python -m pytest \
  tests/services/test_billing_policy.py \
  tests/services/test_credit_service.py \
  tests/models/test_router.py \
  tests/models/test_factory.py \
  tests/gateway/routers/test_models.py \
  tests/dataservice/test_credit_domain.py -v
```

Expected current result: `64 passed`.

```bash
cd /Users/ze/wenjin/.worktrees/admin-model-catalog-pricing/frontend
npm run typecheck
```

Expected current result: exit code `0`.

## File Structure

### Backend Database And DataService

- Create `backend/src/database/models/model_catalog.py`
  - ORM model for `model_catalog_entries`.
  - Enums for provider protocol, category, trust level, health status.
- Create `backend/src/database/models/pricing_policy.py`
  - ORM model for `pricing_policies`.
  - Enum for `PricingPolicyKind`.
- Create `backend/src/database/models/credit_reservation.py`
  - ORM model for `credit_reservations`.
  - Enums for reservation scope/status.
- Modify `backend/src/database/models/user.py`
  - Add `reserved_credits` if reservation implementation uses stored held balance.
- Modify `backend/src/database/models/__init__.py`
  - Export new models/enums.
- Create `backend/alembic/versions/077_model_catalog_pricing_reservations.py`
  - Create new tables, indexes, unique constraints, and user reserved-credit column.
- Create `backend/src/dataservice/domains/model_catalog/contracts.py`
- Create `backend/src/dataservice/domains/model_catalog/repository.py`
- Create `backend/src/dataservice/domains/model_catalog/service.py`
- Create `backend/src/dataservice/domains/model_catalog/security.py`
  - API key encryption/decryption and base URL validation.
- Create `backend/src/dataservice/domains/model_catalog/__init__.py`
- Create `backend/src/dataservice/domains/pricing/contracts.py`
- Create `backend/src/dataservice/domains/pricing/repository.py`
- Create `backend/src/dataservice/domains/pricing/service.py`
- Create `backend/src/dataservice/domains/pricing/__init__.py`
- Modify `backend/src/dataservice/domains/credit/repository.py`
  - Add reservation and reserved balance helpers.
- Modify `backend/src/dataservice/domains/credit/service.py`
  - Add reservation create/settle/release APIs.
- Create `backend/src/dataservice_app/routers/model_catalog.py`
- Create `backend/src/dataservice_app/routers/pricing.py`
- Modify `backend/src/dataservice_app/routers/credit.py`
  - Add reservation endpoints.
- Modify `backend/src/dataservice_app/app.py`
  - Include new internal routers.

### Backend Client, Gateway, Runtime

- Create `backend/src/dataservice_client/contracts/model_catalog.py`
- Create `backend/src/dataservice_client/contracts/pricing.py`
- Modify `backend/src/dataservice_client/contracts/credit.py`
  - Add reservation contracts.
- Modify `backend/src/dataservice_client/client.py`
  - Add model catalog, pricing policy, and reservation methods.
- Create `backend/src/services/model_catalog_service.py`
  - Gateway/admin facade over DataService model catalog.
- Create `backend/src/services/pricing_policy_service.py`
  - Gateway/admin facade and simulator.
- Create `backend/src/services/model_catalog_cache.py`
  - Runtime cache and sync facade over DataService runtime configs.
- Modify `backend/src/config/llm_config.py`
  - Preserve public API but make it read from model catalog cache once implemented.
- Modify `backend/src/models/router.py`
  - Use DB-backed model configs via `llm_config` facade.
- Modify `backend/src/models/factory.py`
  - Use decrypted runtime config and include custom headers in `get_model_full_config`.
- Modify `backend/src/services/billing_policy.py`
  - Replace fixed `TokenBillingPolicy` as runtime source with pricing policy facade while keeping compatibility tests passing during transition.
- Modify `backend/src/services/credit_service.py`
  - Add policy-based charge calculation and reservation wrappers.
- Modify execution/sandbox call sites after locating exact settlement hooks:
  - `backend/src/execution/engine.py`
  - `backend/src/agents/lead_agent/v2/sandbox_runtime.py`
  - `backend/src/task/service.py`
  - `backend/src/task/tasks/base.py`
- Create `backend/src/gateway/routers/admin_models.py`
- Create `backend/src/gateway/routers/admin_pricing.py`
- Modify `backend/src/gateway/routers/models.py`
  - Continue serving user-selectable model list, now DB-backed.
- Modify `backend/src/gateway/app.py`
  - Include admin model/pricing routers.

### Frontend

- Create `frontend/lib/api/admin-models.ts`
- Create `frontend/lib/api/admin-pricing.ts`
- Modify `frontend/lib/api/types.ts`
  - Add model catalog and pricing policy types.
- Modify `frontend/app/dashboard/admin/components/AdminSidebar.tsx`
  - Add Models and Pricing entries.
- Create `frontend/app/dashboard/admin/models/page.tsx`
- Create `frontend/app/dashboard/admin/models/ModelDialog.tsx`
- Create `frontend/app/dashboard/admin/credits/pricing/page.tsx`
- Create `frontend/app/dashboard/admin/credits/pricing/PricingPolicyDialog.tsx`
- Create `frontend/app/dashboard/admin/credits/pricing/PricingSimulator.tsx`

### Tests

- Create `backend/tests/database/test_model_catalog_pricing_models.py`
- Create `backend/tests/dataservice/test_model_catalog_domain.py`
- Create `backend/tests/dataservice/test_pricing_policy_domain.py`
- Extend `backend/tests/dataservice/test_credit_domain.py`
- Create `backend/tests/services/test_model_catalog_service.py`
- Create `backend/tests/services/test_model_catalog_cache.py`
- Create `backend/tests/services/test_pricing_policy_service.py`
- Extend `backend/tests/services/test_billing_policy.py`
- Extend `backend/tests/services/test_credit_service.py`
- Extend `backend/tests/models/test_router.py`
- Extend `backend/tests/models/test_factory.py`
- Extend `backend/tests/gateway/routers/test_models.py`
- Create `backend/tests/gateway/routers/test_admin_models.py`
- Create `backend/tests/gateway/routers/test_admin_pricing.py`
- Create `frontend/tests/unit/admin-models-page.test.tsx`
- Create `frontend/tests/unit/admin-pricing-page.test.tsx`
- Create `frontend/tests/unit/lib/admin-models-api.test.ts`
- Create `frontend/tests/unit/lib/admin-pricing-api.test.ts`

---

### Task 1: Database Models And Migration

**Files:**
- Create: `backend/src/database/models/model_catalog.py`
- Create: `backend/src/database/models/pricing_policy.py`
- Create: `backend/src/database/models/credit_reservation.py`
- Modify: `backend/src/database/models/user.py`
- Modify: `backend/src/database/models/__init__.py`
- Create: `backend/alembic/versions/077_model_catalog_pricing_reservations.py`
- Test: `backend/tests/database/test_model_catalog_pricing_models.py`

- [x] **Step 1: Write ORM contract tests**

Add tests that instantiate the three new ORM models and assert table names, enum values, secret fields, default flags, and `User.reserved_credits`.

```python
def test_model_catalog_entry_contract() -> None:
    from src.database.models.model_catalog import (
        ModelCatalogEntry,
        ModelCategory,
        ModelHealthStatus,
        ModelProviderProtocol,
        ModelTrustLevel,
    )

    assert ModelCatalogEntry.__tablename__ == "model_catalog_entries"
    assert ModelProviderProtocol.OPENAI_COMPATIBLE.value == "openai_compatible"
    assert ModelCategory.LLM.value == "llm"
    assert ModelTrustLevel.CUSTOM.value == "custom"
    assert ModelHealthStatus.UNKNOWN.value == "unknown"
    entry = ModelCatalogEntry(
        model_id="default-model",
        display_name="Default Model",
        provider_protocol=ModelProviderProtocol.OPENAI_COMPATIBLE,
        provider_name="Custom",
        category=ModelCategory.LLM,
        model_name="provider-model",
        base_url="https://api.example.com/v1",
        encrypted_api_key="ciphertext",
        api_key_last4="abcd",
        api_key_fingerprint="fp",
    )
    assert entry.enabled is None or entry.enabled is True
```

- [x] **Step 2: Run the database model tests and verify they fail**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/database/test_model_catalog_pricing_models.py -v
```

Expected: fail with missing modules/classes.

- [x] **Step 3: Add ORM models**

Implement focused ORM models with SQLAlchemy enums using `values_callable`, JSONB-with-JSON fallback, timestamps, and indexes matching the spec. Keep fields string-compatible with existing UUID string patterns.

- [x] **Step 4: Add Alembic migration**

Create revision `077_model_catalog_pricing_reservations` with `down_revision = "076_agent_templates"`. Include:

- `model_catalog_entries`
- `pricing_policies`
- `credit_reservations`
- `users.reserved_credits` integer with default `0`
- partial/unique indexes:
  - `uq_model_catalog_model_id`
  - one default enabled model per category for PostgreSQL
  - `uq_pricing_policy_key`
  - `uq_credit_reservation_idempotency`

- [x] **Step 5: Export models and run tests**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/database/test_model_catalog_pricing_models.py tests/database/test_migration_bootstrap.py -v
```

Expected: pass.

- [x] **Step 6: Commit**

```bash
git add backend/src/database/models backend/alembic/versions/077_model_catalog_pricing_reservations.py backend/tests/database/test_model_catalog_pricing_models.py
git commit -m "feat: add model catalog pricing reservation models"
```

### Task 2: Secret Encryption And URL Safety

**Files:**
- Create: `backend/src/dataservice/domains/model_catalog/security.py`
- Test: `backend/tests/dataservice/test_model_catalog_domain.py`

- [x] **Step 1: Write security tests**

Cover:

- AES-GCM encrypt/decrypt round trip.
- Different AAD fails decrypt.
- API key redaction returns `sk-****abcd`.
- Production URL validator rejects localhost, private IPs, metadata IP, and non-HTTPS.
- Development URL validator allows `http://localhost`.

- [x] **Step 2: Run tests and verify failure**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/dataservice/test_model_catalog_domain.py -v
```

Expected: fail with missing `security.py`.

- [x] **Step 3: Implement security helpers**

Use `cryptography.hazmat.primitives.ciphers.aead.AESGCM`. If `cryptography` is not available in the existing environment, use `Fernet` only if already installed; do not add a new dependency without checking `pyproject.toml`.

Expose:

```python
def encrypt_api_key(api_key: str, *, model_id: str, master_key: bytes) -> str: ...
def decrypt_api_key(ciphertext: str, *, model_id: str, master_key: bytes) -> str: ...
def api_key_last4(api_key: str) -> str: ...
def redact_api_key(last4: str | None) -> str | None: ...
def api_key_fingerprint(api_key: str, *, master_key: bytes) -> str: ...
def validate_model_base_url(base_url: str, *, environment: str) -> None: ...
```

- [x] **Step 4: Add master key loader**

Read `MODEL_SECRET_KEY_FILE` first, then local-development `MODEL_SECRET_KEY`. Require at least 32 bytes after base64/utf8 normalization. Keep this loader in the same security module unless it grows.

- [x] **Step 5: Run tests**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/dataservice/test_model_catalog_domain.py -v
```

Expected: pass.

- [x] **Step 6: Commit**

```bash
git add backend/src/dataservice/domains/model_catalog/security.py backend/tests/dataservice/test_model_catalog_domain.py
git commit -m "feat: add model catalog secret protection"
```

### Task 3: DataService Model Catalog Domain

**Files:**
- Create: `backend/src/dataservice/domains/model_catalog/contracts.py`
- Create: `backend/src/dataservice/domains/model_catalog/repository.py`
- Create: `backend/src/dataservice/domains/model_catalog/service.py`
- Create: `backend/src/dataservice/domains/model_catalog/__init__.py`
- Create: `backend/src/dataservice_app/routers/model_catalog.py`
- Modify: `backend/src/dataservice_app/app.py`
- Create: `backend/src/dataservice_client/contracts/model_catalog.py`
- Modify: `backend/src/dataservice_client/client.py`
- Test: `backend/tests/dataservice/test_model_catalog_domain.py`

- [x] **Step 1: Extend tests for CRUD and invariants**

Add tests for:

- create model encrypts key and returns redacted record.
- list runtime models decrypts key only for internal runtime payload.
- set default unsets previous default.
- cannot disable only enabled default.
- model_id immutable.
- update without `api_key` preserves old encrypted key.
- health update stores redacted error.

- [x] **Step 2: Run failing tests**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/dataservice/test_model_catalog_domain.py -v
```

Expected: fail on missing domain/service methods.

- [x] **Step 3: Implement contracts**

Define Pydantic models:

- `ModelCatalogCreateCommand`
- `ModelCatalogUpdateCommand`
- `ModelCatalogRecord`
- `ModelRuntimeConfig`
- `ModelHealthUpdateCommand`
- `ModelCatalogVersionRecord`

Never include plaintext API key in `ModelCatalogRecord`.

- [x] **Step 4: Implement repository and service**

Keep repository SQL-only and service invariant-heavy. Service owns encryption, default selection, disable rules, version increments, and runtime config assembly.

- [x] **Step 5: Add DataService internal router and client methods**

Internal endpoints:

```text
GET    /internal/v1/model-catalog/models
POST   /internal/v1/model-catalog/models
GET    /internal/v1/model-catalog/models/runtime
PATCH  /internal/v1/model-catalog/models/{model_id}
POST   /internal/v1/model-catalog/models/{model_id}/default
POST   /internal/v1/model-catalog/models/{model_id}/health
```

- [x] **Step 6: Run tests**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/dataservice/test_model_catalog_domain.py -v
```

Expected: pass.

- [x] **Step 7: Commit**

```bash
git add backend/src/dataservice/domains/model_catalog backend/src/dataservice_app backend/src/dataservice_client backend/tests/dataservice/test_model_catalog_domain.py
git commit -m "feat: add dataservice model catalog"
```

### Task 4: Gateway Admin Models API And Public Model List

**Files:**
- Create: `backend/src/services/model_catalog_service.py`
- Create: `backend/src/gateway/routers/admin_models.py`
- Modify: `backend/src/gateway/routers/models.py`
- Modify: `backend/src/gateway/app.py`
- Test: `backend/tests/gateway/routers/test_admin_models.py`
- Test: `backend/tests/gateway/routers/test_models.py`

- [x] **Step 1: Write gateway tests**

Cover:

- admin list models redacts key.
- admin create passes admin id and payload to service.
- admin update with empty key preserves key.
- admin disable returns backend validation errors.
- `/models` lists enabled public models only.

- [x] **Step 2: Run failing tests**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/gateway/routers/test_admin_models.py tests/gateway/routers/test_models.py -v
```

Expected: admin model tests fail before implementation; existing `/models` tests still pass until modified.

- [x] **Step 3: Implement service facade**

`ModelCatalogService` wraps `AsyncDataServiceClient` and keeps browser responses redacted.

- [x] **Step 4: Implement admin router**

Routes:

```text
GET    /api/admin/models
POST   /api/admin/models
PATCH  /api/admin/models/{model_id}
POST   /api/admin/models/{model_id}/disable
POST   /api/admin/models/{model_id}/set-default
POST   /api/admin/models/{model_id}/test
```

Use `get_current_admin`.

- [x] **Step 5: Update public `/models` route**

Keep response shape compatible with current frontend `ModelInfo`; source data from the model catalog service once runtime cache is introduced, or from DataService directly for gateway.

- [x] **Step 6: Run tests and commit**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/gateway/routers/test_admin_models.py tests/gateway/routers/test_models.py -v
```

Commit:

```bash
git add backend/src/services/model_catalog_service.py backend/src/gateway/routers/admin_models.py backend/src/gateway/routers/models.py backend/src/gateway/app.py backend/tests/gateway/routers/test_admin_models.py backend/tests/gateway/routers/test_models.py
git commit -m "feat: expose admin model catalog api"
```

### Task 5: Runtime Model Resolver Cache

**Files:**
- Create: `backend/src/services/model_catalog_cache.py`
- Modify: `backend/src/config/llm_config.py`
- Modify: `backend/src/models/router.py`
- Modify: `backend/src/models/factory.py`
- Test: `backend/tests/services/test_model_catalog_cache.py`
- Test: `backend/tests/models/test_router.py`
- Test: `backend/tests/models/test_factory.py`

- [x] **Step 1: Write cache/factory tests**

Cover:

- cache loads runtime config from fake DataService.
- disabled models are absent from selectable list.
- version change refreshes cache.
- `resolve_model_id("default")` returns catalog default.
- `create_chat_model` uses decrypted runtime config.
- execution-safe model snapshot excludes key.

- [x] **Step 2: Run failing tests**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/services/test_model_catalog_cache.py tests/models/test_router.py tests/models/test_factory.py -v
```

- [x] **Step 3: Implement cache**

Use an immutable snapshot object:

```python
@dataclass(frozen=True)
class RuntimeModelConfig:
    id: str
    name: str
    model: str
    api_key: str
    base_url: str
    max_tokens: int
    temperature: float
    supports_tools: bool
    supports_vision: bool
    supports_thinking: bool
    supports_reasoning_effort: bool
    default_headers: dict[str, str]
```

Provide sync reads over last snapshot and async refresh at request/task boundaries.

- [x] **Step 4: Replace env-backed resolver source**

Keep `llm_config.py` function names (`get_llm_models`, `get_model_config`, `get_model_full_config`, `get_default_model_id`) but redirect to cache snapshot. For tests that still monkeypatch env models, add explicit test helpers rather than production fallback.

- [x] **Step 5: Run tests and commit**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/services/test_model_catalog_cache.py tests/models/test_router.py tests/models/test_factory.py tests/gateway/routers/test_models.py -v
```

Commit:

```bash
git add backend/src/services/model_catalog_cache.py backend/src/config/llm_config.py backend/src/models backend/tests/services/test_model_catalog_cache.py backend/tests/models backend/tests/gateway/routers/test_models.py
git commit -m "feat: route models from dataservice catalog"
```

### Task 6: Pricing Policy Domain And Simulator

**Files:**
- Create: `backend/src/dataservice/domains/pricing/contracts.py`
- Create: `backend/src/dataservice/domains/pricing/repository.py`
- Create: `backend/src/dataservice/domains/pricing/service.py`
- Create: `backend/src/dataservice/domains/pricing/__init__.py`
- Create: `backend/src/dataservice_app/routers/pricing.py`
- Modify: `backend/src/dataservice_app/app.py`
- Create: `backend/src/dataservice_client/contracts/pricing.py`
- Modify: `backend/src/dataservice_client/client.py`
- Create: `backend/src/services/pricing_policy_service.py`
- Create: `backend/src/gateway/routers/admin_pricing.py`
- Modify: `backend/src/gateway/app.py`
- Test: `backend/tests/dataservice/test_pricing_policy_domain.py`
- Test: `backend/tests/services/test_pricing_policy_service.py`
- Test: `backend/tests/gateway/routers/test_admin_pricing.py`

- [x] **Step 1: Write pricing tests**

Cover validators and simulator:

- global credit policy accepts `credits_per_cny=10`.
- model usage policy calculates weighted tokens.
- raw cost guard can dominate weighted token price.
- invalid negative rates are rejected.
- capability policy requires `max_charge_credits >= estimate_max_credits`.
- sandbox policy requires at least one tier.

- [x] **Step 2: Run failing tests**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/dataservice/test_pricing_policy_domain.py tests/services/test_pricing_policy_service.py tests/gateway/routers/test_admin_pricing.py -v
```

- [x] **Step 3: Implement typed policy contracts**

Define:

- `GlobalCreditPolicyConfig`
- `ModelUsagePolicyConfig`
- `CapabilityPricingPolicyConfig`
- `ToolPricingPolicyConfig`
- `SandboxPricingPolicyConfig`
- `PricingSimulationRequest`
- `PricingSimulationResult`

- [x] **Step 4: Implement DataService CRUD**

Routes:

```text
GET    /internal/v1/pricing-policies
POST   /internal/v1/pricing-policies
GET    /internal/v1/pricing-policies/{policy_id}
PATCH  /internal/v1/pricing-policies/{policy_id}
POST   /internal/v1/pricing-policies/{policy_id}/disable
```

- [x] **Step 5: Implement gateway simulator**

`POST /api/admin/pricing/simulate` returns credits, raw cost, margin, and breakdown.

- [x] **Step 6: Run tests and commit**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/dataservice/test_pricing_policy_domain.py tests/services/test_pricing_policy_service.py tests/gateway/routers/test_admin_pricing.py -v
```

Commit:

```bash
git add backend/src/dataservice/domains/pricing backend/src/dataservice_app/routers/pricing.py backend/src/dataservice_client backend/src/services/pricing_policy_service.py backend/src/gateway/routers/admin_pricing.py backend/src/gateway/app.py backend/tests/dataservice/test_pricing_policy_domain.py backend/tests/services/test_pricing_policy_service.py backend/tests/gateway/routers/test_admin_pricing.py
git commit -m "feat: add admin pricing policies"
```

### Task 7: Policy-Based Credit Calculation

**Files:**
- Modify: `backend/src/services/billing_policy.py`
- Modify: `backend/src/services/credit_service.py`
- Modify: `backend/src/dataservice_client/contracts/credit.py`
- Test: `backend/tests/services/test_billing_policy.py`
- Test: `backend/tests/services/test_credit_service.py`

- [x] **Step 1: Write policy-based billing tests**

Add tests:

- weighted token charge replaces fixed `tokens_per_credit`.
- chat min charge applies.
- feature min model charge applies.
- raw cost guard applies when provider cost configured.
- public workflow costs still hide token policy details.

- [x] **Step 2: Run failing tests**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/services/test_billing_policy.py tests/services/test_credit_service.py -v
```

- [x] **Step 3: Implement calculation helpers**

Keep legacy names where needed but add:

```python
def calculate_weighted_tokens(...)
def calculate_model_usage_credits(...)
def calculate_capability_estimate(...)
def calculate_sandbox_estimate(...)
```

- [x] **Step 4: Wire CreditService to pricing service**

Use pricing policies for new paths. Preserve existing transaction metadata keys (`token_usage`, `credits_charged`, `idempotency_key`) so ledger projections continue working.

- [x] **Step 5: Run tests and commit**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/services/test_billing_policy.py tests/services/test_credit_service.py tests/dataservice/test_credit_domain.py -v
```

Commit:

```bash
git add backend/src/services/billing_policy.py backend/src/services/credit_service.py backend/src/dataservice_client/contracts/credit.py backend/tests/services/test_billing_policy.py backend/tests/services/test_credit_service.py
git commit -m "feat: settle credits from pricing policies"
```

### Task 8: Credit Reservations

**Files:**
- Modify: `backend/src/dataservice/domains/credit/repository.py`
- Modify: `backend/src/dataservice/domains/credit/service.py`
- Modify: `backend/src/dataservice_app/routers/credit.py`
- Modify: `backend/src/dataservice_client/contracts/credit.py`
- Modify: `backend/src/dataservice_client/client.py`
- Modify: `backend/src/services/credit_service.py`
- Test: `backend/tests/dataservice/test_credit_domain.py`
- Test: `backend/tests/services/test_credit_concurrency.py`
- Test: `backend/tests/services/test_credit_service.py`

- [ ] **Step 1: Write reservation tests**

Cover:

- create reservation subtracts spendable balance.
- idempotency replay returns same reservation.
- settle creates final credit transaction and releases remainder.
- release returns all reserved credits.
- concurrent reservations cannot exceed spendable balance.
- expired reservations can be released by service method.

- [ ] **Step 2: Run failing tests**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/dataservice/test_credit_domain.py tests/services/test_credit_concurrency.py tests/services/test_credit_service.py -v
```

- [ ] **Step 3: Implement reservation repository/service**

Add DataService methods:

```python
create_reservation(...)
settle_reservation(...)
release_reservation(...)
```

Use user row locks and idempotency keys.

- [ ] **Step 4: Add internal endpoints and client methods**

Routes:

```text
POST /internal/v1/credit/reservations
POST /internal/v1/credit/reservations/{reservation_id}/settle
POST /internal/v1/credit/reservations/{reservation_id}/release
```

- [ ] **Step 5: Add CreditService wrappers**

Expose:

```python
reserve_for_feature_execution(...)
settle_feature_reservation(...)
reserve_for_sandbox_operation(...)
settle_sandbox_reservation(...)
release_reservation(...)
```

- [ ] **Step 6: Run tests and commit**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/dataservice/test_credit_domain.py tests/services/test_credit_concurrency.py tests/services/test_credit_service.py -v
```

Commit:

```bash
git add backend/src/dataservice/domains/credit backend/src/dataservice_app/routers/credit.py backend/src/dataservice_client backend/src/services/credit_service.py backend/tests/dataservice/test_credit_domain.py backend/tests/services/test_credit_concurrency.py backend/tests/services/test_credit_service.py
git commit -m "feat: add credit reservations"
```

### Task 9: Execution And Sandbox Integration

**Files:**
- Modify: `backend/src/execution/engine.py`
- Modify: `backend/src/agents/lead_agent/v2/sandbox_runtime.py`
- Modify: `backend/src/task/service.py`
- Modify: `backend/src/task/tasks/base.py`
- Test: existing execution/sandbox/task tests plus new targeted tests after locating exact hooks.

- [ ] **Step 1: Locate current billing hooks**

Run:

```bash
cd backend
rg -n "consume_for_feature_usage|consume_for_sandbox_operation|refund_consumption|credit_transaction_id|billing" src tests
```

Record exact functions in comments inside this plan if they differ from expected files.

- [ ] **Step 2: Write integration tests**

Add/extend tests to cover:

- feature launch creates reservation before enqueue.
- successful execution settles reservation from measured usage.
- failed execution releases or refunds reservation.
- sandbox Python reserves before acquiring sandbox and settles actual usage.

- [ ] **Step 3: Run failing tests**

Run targeted tests discovered in Step 1.

- [ ] **Step 4: Implement feature reservation integration**

At launch, compute capability estimate/max and reserve. Store `credit_reservation_id` in runtime/execution metadata. At completion, settle with collected model/tool/sandbox usage.

- [ ] **Step 5: Implement sandbox reservation integration**

Reserve before acquiring sandbox. Settle with actual duration/tier. Platform acquisition failure releases reservation.

- [ ] **Step 6: Run tests and commit**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/agents/lead_agent/v2/test_sandbox_runtime.py tests/services/test_credit_service.py tests/task -v
```

Commit:

```bash
git add backend/src/execution backend/src/agents/lead_agent/v2/sandbox_runtime.py backend/src/task backend/tests
git commit -m "feat: reserve and settle execution credits"
```

### Task 10: Seed Import And Release Gates

**Files:**
- Create: `backend/src/dataservice/domains/model_catalog/seed_loader.py`
- Modify: `backend/src/dataservice/domains/catalog/seed_loader.py` only if existing seed orchestration should call model seed.
- Modify: `backend/src/quality` or existing release gate files after locating exact gate implementation.
- Test: `backend/tests/integration/test_capability_skill_seeds.py`
- Test: `backend/tests/quality/test_release_gate_cli.py`

- [ ] **Step 1: Locate release gate and seed patterns**

Run:

```bash
cd backend
rg -n "release_gate|ReleaseGate|load_seeds|seed" src tests/quality tests/integration
```

- [ ] **Step 2: Write tests**

Cover:

- imports current config/env models when catalog empty.
- does not overwrite existing catalog.
- release gate fails without enabled default model.
- release gate fails when enabled model lacks pricing policy.

- [ ] **Step 3: Implement seed import**

Read current `LLM_MODELS` / config only as seed input. After import, runtime source remains DataService.

- [ ] **Step 4: Implement release gates**

Add gate checks listed in the spec.

- [ ] **Step 5: Run tests and commit**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/integration/test_capability_skill_seeds.py tests/quality/test_release_gate_cli.py tests/quality/test_architecture_gate_configuration.py -v
```

Commit:

```bash
git add backend/src backend/tests/integration backend/tests/quality
git commit -m "feat: seed model catalog and enforce pricing gates"
```

### Task 11: Admin Frontend Models And Pricing Pages

**Files:**
- Create: `frontend/lib/api/admin-models.ts`
- Create: `frontend/lib/api/admin-pricing.ts`
- Modify: `frontend/lib/api/types.ts`
- Modify: `frontend/app/dashboard/admin/components/AdminSidebar.tsx`
- Create: `frontend/app/dashboard/admin/models/page.tsx`
- Create: `frontend/app/dashboard/admin/models/ModelDialog.tsx`
- Create: `frontend/app/dashboard/admin/credits/pricing/page.tsx`
- Create: `frontend/app/dashboard/admin/credits/pricing/PricingPolicyDialog.tsx`
- Create: `frontend/app/dashboard/admin/credits/pricing/PricingSimulator.tsx`
- Test: `frontend/tests/unit/admin-models-page.test.tsx`
- Test: `frontend/tests/unit/admin-pricing-page.test.tsx`
- Test: `frontend/tests/unit/lib/admin-models-api.test.ts`
- Test: `frontend/tests/unit/lib/admin-pricing-api.test.ts`

- [ ] **Step 1: Write API client tests**

Mock `apiClient` and assert endpoint paths:

- `GET /admin/models`
- `POST /admin/models`
- `PATCH /admin/models/{id}`
- `POST /admin/models/{id}/test`
- `GET /admin/pricing-policies`
- `POST /admin/pricing/simulate`

- [ ] **Step 2: Write page tests**

Cover:

- API key displays as redacted.
- save with empty key does not send `api_key`.
- disable default model error displays.
- pricing simulator renders credit estimate and margin.

- [ ] **Step 3: Run failing frontend tests**

Run:

```bash
cd frontend
npx vitest run frontend/tests/unit/admin-models-page.test.tsx frontend/tests/unit/admin-pricing-page.test.tsx frontend/tests/unit/lib/admin-models-api.test.ts frontend/tests/unit/lib/admin-pricing-api.test.ts
```

- [ ] **Step 4: Implement API clients**

Follow existing `admin-credit-rules.ts` style. Keep types explicit and avoid returning API key plaintext.

- [ ] **Step 5: Implement admin pages**

Use existing admin visual language. Avoid nested cards. Use compact tables, dialogs, badges, and explicit destructive confirmations.

- [ ] **Step 6: Add sidebar entries**

Add:

- Business section: `模型管理`
- Credit group child: `定价策略`

- [ ] **Step 7: Run tests and commit**

Run:

```bash
cd frontend
npm run typecheck
npx vitest run frontend/tests/unit/admin-models-page.test.tsx frontend/tests/unit/admin-pricing-page.test.tsx frontend/tests/unit/lib/admin-models-api.test.ts frontend/tests/unit/lib/admin-pricing-api.test.ts
```

Commit:

```bash
git add frontend/lib/api frontend/app/dashboard/admin frontend/tests/unit
git commit -m "feat: add admin model and pricing pages"
```

### Task 12: Final Review And Verification

**Files:**
- All changed files.

- [ ] **Step 1: Run backend lint**

```bash
cd backend
.venv/bin/ruff check src tests
```

Expected: `All checks passed!`

- [ ] **Step 2: Run backend full tests**

```bash
cd backend
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy -u NO_PROXY -u no_proxy \
  .venv/bin/python -m pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 3: Run frontend checks**

```bash
cd frontend
npm run typecheck
npm test
npm run build
```

Expected: typecheck, Vitest, and production build pass.

- [ ] **Step 4: Run migration smoke**

```bash
cd backend
.venv/bin/python -m alembic upgrade head
```

Expected: migration reaches latest head in local configured DB. If local DB is unavailable, report that explicitly and rely on migration bootstrap tests.

- [ ] **Step 5: Manual browser check**

Start dev server:

```bash
cd frontend
npm run dev
```

Open admin pages in the local browser:

- `/dashboard/admin/models`
- `/dashboard/admin/credits/pricing`

Verify no layout overlap and key fields redact secrets.

- [ ] **Step 6: Final git review**

```bash
git status --short --branch
git log --oneline --decorate -12
git diff --stat origin/master..HEAD
```

- [ ] **Step 7: Commit final cleanup if needed**

Only commit if verification caused doc/test cleanup.

```bash
git add <files>
git commit -m "test: verify admin model pricing system"
```

## Execution Notes

- Do not expose plaintext API keys in browser responses, logs, or admin audit records.
- Do not preserve production fallback to `LLM_MODELS` after the DataService catalog is active. Legacy config is seed input only.
- Keep public `/models` response backward compatible for existing frontend model pickers.
- Prefer soft disable over hard delete for model records and pricing policies.
- Each task should leave tests passing for its touched area and should be committed before moving to the next task.
