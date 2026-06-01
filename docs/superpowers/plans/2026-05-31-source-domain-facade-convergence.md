# Source Domain Facade Convergence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete Phase 2 of the architecture hotspot spec by reducing `SourceDataDomainService` into a facade backed by focused source-domain services without changing external behavior.

**Architecture:** `SourceDataDomainService` remains the only public DataService domain entry used by routers and DataService APIs. It owns a shared `SourceDomainContext` and delegates to `SourceImportService`, `SourceAssetService`, `SourceBibliographyService`, `SourceProjectionService`, and `SourceIndexService`. Shared serialization and normalization helpers move to `helpers.py`; repository access remains through `SourceRepository` and `ProvenanceRepository`.

**Tech Stack:** Python 3.13, SQLAlchemy async session, Pydantic v2 contracts, pytest, ruff.

---

## File Structure

- Create `backend/src/dataservice/domains/source/context.py`: shared `SourceDomainContext`, repository/provenance repository holders, and `_finish()` commit/flush behavior.
- Create `backend/src/dataservice/domains/source/helpers.py`: pure helpers for citation key normalization, id normalization, DOI cleanup, BibTeX rendering, and source/reference/asset/outline/text-unit serializers.
- Create `backend/src/dataservice/domains/source/import_service.py`: source create/upsert/import/update/delete/status/external-id methods.
- Create `backend/src/dataservice/domains/source/asset_service.py`: source asset link/get/update/list methods.
- Create `backend/src/dataservice/domains/source/bibliography_service.py`: bibliography build/snapshot plus citation usage/provenance methods.
- Create `backend/src/dataservice/domains/source/index_service.py`: source outline, text-unit search/read, index replace, evidence pack support.
- Create `backend/src/dataservice/domains/source/projection_service.py`: source detail/list/page/count/library outline/workspace TOC methods.
- Modify `backend/src/dataservice/domains/source/service.py`: facade constructor, repository property compatibility, and delegating public methods.
- Modify `backend/tests/architecture/test_dataservice_boundaries.py`: architecture guard that keeps the facade below 350 lines and requires focused source subservices.

## Task 1: Add Source Facade Architecture Guard

**Files:**
- Modify: `backend/tests/architecture/test_dataservice_boundaries.py`

- [ ] **Step 1: Write the failing architecture test**

Add this test near the existing DataService domain architecture guards:

```python
def test_source_domain_service_is_facade_over_focused_services() -> None:
    """Source domain public service should stay a facade over focused services."""
    source_root = SRC_ROOT / "dataservice" / "domains" / "source"
    expected_files = {
        "context.py",
        "helpers.py",
        "import_service.py",
        "asset_service.py",
        "bibliography_service.py",
        "index_service.py",
        "projection_service.py",
    }
    missing = [name for name in sorted(expected_files) if not (source_root / name).exists()]
    assert not missing, f"Missing focused source services: {missing}"

    service_lines = (source_root / "service.py").read_text(encoding="utf-8").splitlines()
    assert len(service_lines) < 350
    service_source = "\n".join(service_lines)
    assert "SourceImportService" in service_source
    assert "SourceAssetService" in service_source
    assert "SourceBibliographyService" in service_source
    assert "SourceProjectionService" in service_source
    assert "SourceIndexService" in service_source
    assert "def _format_bibtex_entry(" not in service_source
    assert "def _serialize_reference_projection(" not in service_source
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/architecture/test_dataservice_boundaries.py::test_source_domain_service_is_facade_over_focused_services -q
```

Expected: FAIL because the focused source service files do not exist and `service.py` is still about 1200 lines.

## Task 2: Extract Shared Context and Helpers

**Files:**
- Create: `backend/src/dataservice/domains/source/context.py`
- Create: `backend/src/dataservice/domains/source/helpers.py`

- [ ] **Step 1: Create `SourceDomainContext`**

Implement:

```python
@dataclass(slots=True)
class SourceDomainContext:
    session: AsyncSession
    repository: SourceRepository
    provenance_repository: ProvenanceRepository
    autocommit: bool = True

    async def finish(self) -> None:
        if self.autocommit:
            await self.session.commit()
        else:
            await self.session.flush()
```

- [ ] **Step 2: Move pure helpers**

Move these functions unchanged into `helpers.py`:

- `normalize_citation_keys`
- `normalize_ids`
- `max_ranked_value`
- `format_bibtex_entry`
- `clean_bibtex_value`
- `clean_citation_key`
- `normalize_doi`
- `serialize_reference_projection`
- `serialize_source_asset`
- `serialize_external_id`
- `serialize_outline_node`
- `serialize_text_unit`

Keep `_PROCEEDINGS_BIBTEX_TYPES = {"conference", "inproceedings", "proceedings"}` in `helpers.py`.

- [ ] **Step 3: Run helper import check**

Run:

```bash
cd backend && .venv/bin/python - <<'PY'
from src.dataservice.domains.source.helpers import normalize_doi, clean_citation_key
assert normalize_doi("https://doi.org/10.1000/ABC") == "10.1000/abc"
assert clean_citation_key("", default_key="source") == "source"
PY
```

Expected: command exits 0.

## Task 3: Extract Import and Asset Services

**Files:**
- Create: `backend/src/dataservice/domains/source/import_service.py`
- Create: `backend/src/dataservice/domains/source/asset_service.py`

- [ ] **Step 1: Implement `SourceImportService`**

Move these methods from `SourceDataDomainService` into `SourceImportService`, replacing `self.repository` with `self.context.repository`, `self._finish()` with `self.context.finish()`, and helper calls with imports from `helpers.py`:

- `create_source`
- `upsert_source`
- `import_source`
- `upsert_source_external_ids`
- `list_source_external_ids`
- `mark_deleted`
- `mark_deleted_for_workspace`
- `update_source`
- `mark_status`
- `_ensure_unique_citation_key`
- `_find_import_source`
- `_merge_import_values`

Constructor:

```python
class SourceImportService:
    def __init__(self, context: SourceDomainContext) -> None:
        self.context = context
```

- [ ] **Step 2: Implement `SourceAssetService`**

Move these methods into `SourceAssetService`:

- `link_source_asset`
- `get_source_asset`
- `update_source_asset`
- `list_source_assets`

Use `serialize_source_asset()` from `helpers.py`.

- [ ] **Step 3: Run characterization tests for import/assets**

Run:

```bash
cd backend && .venv/bin/python -m pytest \
  tests/dataservice/test_source_provenance_domain.py::test_source_service_normalizes_title_and_lists_active_sources \
  tests/dataservice/test_source_provenance_domain.py::test_source_service_imports_and_dedupes_by_external_id \
  tests/dataservice/test_source_provenance_domain.py::test_source_service_links_source_assets \
  tests/dataservice/test_source_provenance_domain.py::test_source_service_updates_source_asset_status_and_metadata \
  -q
```

Expected: PASS after facade delegates these methods.

## Task 4: Extract Bibliography and Index Services

**Files:**
- Create: `backend/src/dataservice/domains/source/bibliography_service.py`
- Create: `backend/src/dataservice/domains/source/index_service.py`

- [ ] **Step 1: Implement `SourceBibliographyService`**

Move these methods:

- `build_bibliography`
- `create_bibliography_snapshot`
- `list_sources_by_citation_keys`
- `record_citation_usage`

Use `format_bibtex_entry()`, `normalize_ids()`, and `normalize_citation_keys()` from `helpers.py`.

- [ ] **Step 2: Implement `SourceIndexService`**

Move these methods:

- `get_source_outline`
- `search_text_units`
- `search_workspace_sections`
- `get_source_section`
- `get_source_section_by_title`
- `read_source_outline_node`
- `read_source_pages`
- `replace_source_index`
- `_section_from_node`

Use `serialize_outline_node()` and `serialize_text_unit()` from `helpers.py`.

- [ ] **Step 3: Run characterization tests for bibliography/index/usage**

Run:

```bash
cd backend && .venv/bin/python -m pytest \
  tests/dataservice/test_source_provenance_domain.py::test_source_service_builds_bibliography_from_sources \
  tests/dataservice/test_source_provenance_domain.py::test_source_service_creates_bibliography_snapshot \
  tests/dataservice/test_source_provenance_domain.py::test_source_service_replaces_source_index \
  tests/dataservice/test_source_provenance_domain.py::test_source_service_builds_evidence_pack_from_source_index \
  tests/dataservice/test_source_provenance_domain.py::test_source_service_records_citation_usage_as_provenance \
  -q
```

Expected: PASS after facade delegates these methods and composes `build_evidence_pack`.

## Task 5: Extract Projection Service and Replace Facade

**Files:**
- Create: `backend/src/dataservice/domains/source/projection_service.py`
- Replace: `backend/src/dataservice/domains/source/service.py`

- [ ] **Step 1: Implement `SourceProjectionService`**

Move these methods:

- `get_source`
- `get_source_for_workspace`
- `get_source_detail`
- `list_sources`
- `list_sources_page`
- `count_sources`
- `count_reference_summary`
- `get_library_outline`
- `get_workspace_toc_summary`

Constructor accepts `SourceDomainContext`, `SourceAssetService`, and `SourceIndexService` so projections can load assets and outlines.

- [ ] **Step 2: Replace `SourceDataDomainService` with facade**

`service.py` should:

- create `SourceDomainContext`
- instantiate focused services
- expose `repository` and `provenance_repository` properties for current tests and controlled dependency replacement
- proxy all existing public methods to the focused services
- implement `build_evidence_pack()` as composition of `projection_service.get_library_outline()` and `index_service.search_text_units()`

The public method list remains:

```text
create_source, upsert_source, import_source, get_source, get_source_for_workspace,
get_source_detail, upsert_source_external_ids, list_source_external_ids,
build_bibliography, create_bibliography_snapshot, mark_deleted,
link_source_asset, get_source_asset, update_source_asset, mark_deleted_for_workspace,
update_source, mark_status, list_sources, list_sources_page, count_sources,
count_reference_summary, get_library_outline, get_workspace_toc_summary,
list_source_assets, get_source_outline, search_text_units, build_evidence_pack,
search_workspace_sections, get_source_section, get_source_section_by_title,
read_source_outline_node, read_source_pages, replace_source_index,
list_sources_by_citation_keys, record_citation_usage
```

- [ ] **Step 3: Run full source domain tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/dataservice/test_source_provenance_domain.py -q
```

Expected: PASS.

## Task 6: Verify Architecture and Backend

**Files:**
- All files touched by this plan.

- [ ] **Step 1: Run ruff**

Run:

```bash
cd backend && .venv/bin/ruff check src/dataservice/domains/source tests/architecture/test_dataservice_boundaries.py --fix
```

Expected: all import/order issues fixed.

- [ ] **Step 2: Run architecture and source tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/architecture tests/dataservice/test_source_provenance_domain.py -q
```

Expected: PASS.

- [ ] **Step 3: Check file-size targets**

Run:

```bash
wc -l backend/src/dataservice/domains/source/service.py backend/src/dataservice/domains/source/*_service.py backend/src/dataservice/domains/source/helpers.py backend/src/dataservice/domains/source/context.py
```

Expected: `service.py` below 350 lines and each `*_service.py` below 500 lines.

- [ ] **Step 4: Run full backend tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/ -q
```

Expected: PASS.

## Task 7: Commit and Push

**Files:**
- Stage source-domain split, architecture tests, and this plan.

- [ ] **Step 1: Inspect status**

Run:

```bash
git status --short
```

Expected: only source-domain split files, architecture tests, and plan/docs changes are uncommitted.

- [ ] **Step 2: Commit**

Run:

```bash
git add backend/src/dataservice/domains/source \
  backend/tests/architecture/test_dataservice_boundaries.py \
  docs/superpowers/plans/2026-05-31-source-domain-facade-convergence.md
git commit -m "refactor: split source domain service facade"
git push
```

Expected: commit and push succeed on the current branch.

## Self-review

- Spec coverage: implements Phase 2 Source domain convergence from the architecture hotspot spec.
- Scope boundary: does not change Source DataService contracts, routers, repositories, or database schema.
- Behavior coverage: existing source provenance tests cover create/list/count/import dedupe/index/evidence/asset/bibliography/snapshot/citation usage paths.
- Placeholder scan: no placeholder markers.
