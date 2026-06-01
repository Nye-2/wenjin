# DataService Client Mixin Convergence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete Phase 1 of the architecture hotspot spec by moving DataService client domain APIs out of `client.py` into focused mixins while keeping `AsyncDataServiceClient`'s public API unchanged.

**Architecture:** `AsyncDataServiceClient` remains the public shell and owns `_request`, auth headers, health checks, and context-manager lifecycle. Domain API groups live in mixin modules and are mounted through multiple inheritance. Architecture tests prevent execution/source/credit/model/pricing/sandbox methods from drifting back into `client.py`.

**Tech Stack:** Python 3.13, httpx, Pydantic v2 contracts, pytest, ruff.

---

## File Structure

- Create `backend/src/dataservice_client/source_client.py`: source/reference/bibliography/evidence/provenance client methods.
- Create `backend/src/dataservice_client/credit_client.py`: credit balance/history/consumption/reservation/grant/redeem/referral methods.
- Create `backend/src/dataservice_client/model_catalog_client.py`: model catalog and runtime model methods.
- Create `backend/src/dataservice_client/pricing_client.py`: pricing simulation and pricing policy methods.
- Create `backend/src/dataservice_client/sandbox_client.py`: sandbox environment/job/lease/artifact methods.
- Modify `backend/src/dataservice_client/client.py`: remove moved contract imports and methods; inherit from new mixins.
- Modify `backend/tests/architecture/test_dataservice_boundaries.py`: add domain-mixin guard.
- Modify `backend/tests/dataservice/test_foundation.py`: keep existing MockTransport client contract tests as behavioral coverage; add explicit smoke calls if a moved domain lacks direct contract coverage.
- Keep `backend/src/dataservice_client/execution_client.py` unchanged except for import formatting if ruff requires it.

## Task 1: Add Architecture Guard First

**Files:**
- Modify: `backend/tests/architecture/test_dataservice_boundaries.py`

- [ ] **Step 1: Write the failing architecture test**

Add this test next to `test_dataservice_client_execution_api_lives_in_dedicated_mixin`:

```python
def test_dataservice_client_domain_apis_live_in_dedicated_mixins() -> None:
    """Keep domain DataService APIs out of the generic HTTP client shell."""
    client_path = SRC_ROOT / "dataservice_client" / "client.py"
    client_source = client_path.read_text(encoding="utf-8")
    expected = {
        "SourceDataServiceClientMixin": {
            "file": SRC_ROOT / "dataservice_client" / "source_client.py",
            "forbidden_methods": [
                "async def create_source(",
                "async def import_source(",
                "async def list_sources(",
                "async def build_source_bibliography(",
                "async def create_provenance_link(",
            ],
        },
        "CreditDataServiceClientMixin": {
            "file": SRC_ROOT / "dataservice_client" / "credit_client.py",
            "forbidden_methods": [
                "async def get_credit_summary(",
                "async def record_credit_consumption(",
                "async def create_credit_reservation(",
                "async def create_credit_redeem_code(",
                "async def record_credit_referral(",
            ],
        },
        "ModelCatalogDataServiceClientMixin": {
            "file": SRC_ROOT / "dataservice_client" / "model_catalog_client.py",
            "forbidden_methods": [
                "async def list_model_catalog_models(",
                "async def create_model_catalog_model(",
                "async def update_model_catalog_health(",
                "async def list_model_catalog_runtime_models(",
            ],
        },
        "PricingDataServiceClientMixin": {
            "file": SRC_ROOT / "dataservice_client" / "pricing_client.py",
            "forbidden_methods": [
                "async def simulate_pricing(",
                "async def list_pricing_policies(",
                "async def create_pricing_policy(",
                "async def disable_pricing_policy(",
            ],
        },
        "SandboxDataServiceClientMixin": {
            "file": SRC_ROOT / "dataservice_client" / "sandbox_client.py",
            "forbidden_methods": [
                "async def create_sandbox_environment(",
                "async def get_or_create_sandbox_environment(",
                "async def create_sandbox_job(",
                "async def acquire_sandbox_lease(",
                "async def register_sandbox_artifact(",
            ],
        },
    }
    for mixin, config in expected.items():
        assert config["file"].exists(), f"{mixin} module is missing"
        assert mixin in client_source
        for method in config["forbidden_methods"]:
            assert method not in client_source
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/architecture/test_dataservice_boundaries.py::test_dataservice_client_domain_apis_live_in_dedicated_mixins -q
```

Expected: FAIL because the new mixin files do not exist and the methods still live in `client.py`.

## Task 2: Move Credit Methods

**Files:**
- Create: `backend/src/dataservice_client/credit_client.py`
- Modify: `backend/src/dataservice_client/client.py`

- [ ] **Step 1: Create `CreditDataServiceClientMixin`**

Move methods from `client.py` lines starting at `list_credit_grant_rules` through `apply_credit_referrer_first_task_bonus` into `credit_client.py`. The file imports:

```python
from __future__ import annotations

from datetime import datetime
from typing import Any

from src.dataservice_client.contracts.credit import (
    CreditAdminAdjustPayload,
    CreditAdminSummaryPayload,
    CreditConsumptionCreatePayload,
    CreditConsumptionStatsPayload,
    CreditGrantRuleCreatePayload,
    CreditGrantRulePayload,
    CreditGrantRuleUpdatePayload,
    CreditHistoryPayload,
    CreditPeriodicGrantProcessPayload,
    CreditPeriodicGrantSummaryPayload,
    CreditRedeemCodeCreatePayload,
    CreditRedeemCodePayload,
    CreditRedeemPayload,
    CreditReferralCreatePayload,
    CreditReferralPayload,
    CreditRefundPayload,
    CreditReservationCreatePayload,
    CreditReservationPayload,
    CreditReservationReleasePayload,
    CreditReservationSettlePayload,
    CreditSummaryPayload,
    CreditTokenUsagePayload,
    CreditTransactionPayload,
)
```

Define:

```python
class CreditDataServiceClientMixin:
    async def _request(self, method: str, path: str, *, authenticated: bool = True, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError
```

- [ ] **Step 2: Mount the mixin**

Update `client.py`:

```python
from src.dataservice_client.credit_client import CreditDataServiceClientMixin

class AsyncDataServiceClient(
    ExecutionDataServiceClientMixin,
    CreditDataServiceClientMixin,
):
    ...
```

Remove the credit contract import block from `client.py`.

- [ ] **Step 3: Run focused tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/dataservice/test_foundation.py tests/architecture/test_dataservice_boundaries.py::test_dataservice_client_domain_apis_live_in_dedicated_mixins -q
```

Expected: architecture test still fails until all domain mixins are moved; foundation tests should continue passing for moved credit methods.

## Task 3: Move Model Catalog and Pricing Methods

**Files:**
- Create: `backend/src/dataservice_client/model_catalog_client.py`
- Create: `backend/src/dataservice_client/pricing_client.py`
- Modify: `backend/src/dataservice_client/client.py`

- [ ] **Step 1: Move model catalog methods**

Move these methods into `ModelCatalogDataServiceClientMixin`:

- `list_model_catalog_models`
- `get_model_catalog_model`
- `create_model_catalog_model`
- `update_model_catalog_model`
- `set_model_catalog_default`
- `update_model_catalog_health`
- `list_model_catalog_runtime_models`

Use imports from `src.dataservice_client.contracts.model_catalog`.

- [ ] **Step 2: Move pricing methods**

Move these methods into `PricingDataServiceClientMixin`:

- `simulate_pricing`
- `list_pricing_policies`
- `get_pricing_policy`
- `create_pricing_policy`
- `update_pricing_policy`
- `disable_pricing_policy`

Use imports from `src.dataservice_client.contracts.pricing`.

- [ ] **Step 3: Mount both mixins and run tests**

Update class inheritance and imports in `client.py`, then run:

```bash
cd backend && .venv/bin/python -m pytest tests/dataservice/test_foundation.py tests/architecture/test_dataservice_boundaries.py::test_dataservice_client_domain_apis_live_in_dedicated_mixins -q
```

Expected: architecture test still fails until source and sandbox are moved; model/pricing MockTransport tests pass.

## Task 4: Move Source and Provenance Methods

**Files:**
- Create: `backend/src/dataservice_client/source_client.py`
- Modify: `backend/src/dataservice_client/client.py`

- [ ] **Step 1: Create `SourceDataServiceClientMixin`**

Move methods from `create_source` through `delete_provenance_links` into `source_client.py`. Include source and provenance contract imports:

```python
from src.dataservice_client.contracts.provenance import (
    ProvenanceLinkCreatePayload,
    ProvenanceLinkPayload,
)
from src.dataservice_client.contracts.source import (
    SourceAssetLinkPayload,
    SourceAssetUpdatePayload,
    SourceBibliographyCreatePayload,
    SourceBibliographyPayload,
    SourceBibliographySnapshotCreatePayload,
    SourceBibliographySnapshotPayload,
    SourceCitationUsageCreatePayload,
    SourceCitationUsagePayload,
    SourceCreatePayload,
    SourceEvidencePackCreatePayload,
    SourceEvidencePackPayload,
    SourceExternalIdCreatePayload,
    SourceImportPayload,
    SourceImportResultPayload,
    SourceIndexReplacePayload,
    SourcePayload,
    SourceUpdatePayload,
)
```

- [ ] **Step 2: Mount the mixin and run tests**

Update `client.py` inheritance and remove source/provenance imports, then run:

```bash
cd backend && .venv/bin/python -m pytest tests/dataservice/test_foundation.py tests/architecture/test_dataservice_boundaries.py::test_dataservice_client_domain_apis_live_in_dedicated_mixins -q
```

Expected: architecture test still fails until sandbox is moved; source MockTransport tests pass.

## Task 5: Move Sandbox Methods

**Files:**
- Create: `backend/src/dataservice_client/sandbox_client.py`
- Modify: `backend/src/dataservice_client/client.py`

- [ ] **Step 1: Create `SandboxDataServiceClientMixin`**

Move methods from `create_sandbox_environment` through `list_sandbox_artifacts` into `sandbox_client.py`. Use imports from `src.dataservice_client.contracts.sandbox`.

- [ ] **Step 2: Mount the mixin and run the architecture test**

Update `client.py` inheritance and imports, then run:

```bash
cd backend && .venv/bin/python -m pytest tests/architecture/test_dataservice_boundaries.py::test_dataservice_client_domain_apis_live_in_dedicated_mixins -q
```

Expected: PASS.

## Task 6: Clean Imports, Format, and Verify

**Files:**
- Modify as needed: moved mixin files and `backend/src/dataservice_client/client.py`

- [ ] **Step 1: Run ruff**

Run:

```bash
cd backend && .venv/bin/ruff check src/dataservice_client tests/architecture/test_dataservice_boundaries.py --fix
```

Expected: all import ordering and unused imports fixed.

- [ ] **Step 2: Run focused backend tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/dataservice/test_foundation.py tests/architecture -q
```

Expected: PASS.

- [ ] **Step 3: Check file-size target**

Run:

```bash
wc -l backend/src/dataservice_client/client.py backend/src/dataservice_client/*_client.py
```

Expected: `client.py` below 2200 lines for Phase 1.

- [ ] **Step 4: Run full backend tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/ -q
```

Expected: PASS.

## Task 7: Commit

**Files:**
- Stage all files touched by this plan.

- [ ] **Step 1: Inspect status**

Run:

```bash
git status --short
```

Expected: only the spec, this plan, DataService client mixins, architecture tests, and import cleanup are changed.

- [ ] **Step 2: Commit**

Run:

```bash
git add docs/superpowers/specs/2026-05-31-architecture-hotspot-convergence-design.md \
  docs/superpowers/plans/2026-05-31-dataservice-client-mixin-convergence.md \
  backend/src/dataservice_client/client.py \
  backend/src/dataservice_client/*_client.py \
  backend/tests/architecture/test_dataservice_boundaries.py
git commit -m "refactor: split dataservice client domain mixins"
```

Expected: commit succeeds.

## Self-review

- Spec coverage: covers Phase 1 DataService client mixin split from the architecture hotspot spec. Source domain, frontend components, upload/sandbox runtime, and dead-code cleanup remain future plans.
- Placeholder scan: no placeholder markers.
- Type consistency: mixin classes expose `_request()` with the same signature as `AsyncDataServiceClient._request()`, so moved methods can call `self._request()` unchanged.
- Risk boundary: external business code still uses `AsyncDataServiceClient`; no API shape changes are planned.
