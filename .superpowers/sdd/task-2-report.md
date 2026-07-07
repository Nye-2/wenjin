# Task 2 Report: Research Loop Methodology Contract

## Scope

- Updated methodology contracts for:
  - `backend/seed/capabilities/sci/research_question_to_paper.yaml`
  - `backend/seed/capabilities/sci/sci_literature_positioning.yaml`
  - `backend/seed/capabilities/thesis/thesis_research_pack.yaml`
- Added/updated tests for exact stage ids, required artifacts, completion gates, and TeamKernel methodology projection.

## RED

Commands run before YAML changes:

```bash
cd backend && .venv/bin/python -m pytest tests/integration/test_capability_skill_seeds.py::test_sci_capability_methodology_samples_are_parseable_and_specific -v
cd backend && .venv/bin/python -m pytest tests/architecture/test_academic_harness_catalog.py -v
cd backend && .venv/bin/python -m pytest tests/agents/lead_agent/v2/test_team_member_context.py -v
```

Observed failures:

- `test_sci_capability_methodology_samples_are_parseable_and_specific`
  - failed because `sci_literature_positioning` still exposed old stage ids: `intent`, `triage`, `deepen`, `synthesize`
- `test_representative_research_capabilities_expose_research_loop_methodology`
  - failed because `research_question_to_paper` still exposed old stage ids: `project_context`, `architecture`, `evidence_probe`, `draft`, `audit_compress`
- `test_team_member_context.py -v`
  - passed, confirming `_methodology_contract` already projected stage ids, artifacts, claim policy, retrieval policy, and completion gates correctly once provided

## GREEN

Commands run after YAML updates:

```bash
cd backend && .venv/bin/python -m pytest tests/integration/test_capability_skill_seeds.py::test_sci_capability_methodology_samples_are_parseable_and_specific -v
cd backend && .venv/bin/python -m pytest tests/architecture/test_academic_harness_catalog.py -v
cd backend && .venv/bin/python -m pytest tests/agents/lead_agent/v2/test_team_member_context.py -v
```

Observed results:

- `tests/integration/test_capability_skill_seeds.py::test_sci_capability_methodology_samples_are_parseable_and_specific` passed
- `tests/architecture/test_academic_harness_catalog.py` passed (`6 passed`)
- `tests/agents/lead_agent/v2/test_team_member_context.py` passed (`9 passed`)

## Self-review

- Kept changes limited to backend capability contracts and backend tests.
- Did not touch Chat Agent prompts, frontend files, or Task 1 coverage.
- Confirmed `member_context.py` needed no production change; added only targeted projection coverage for multi-stage facet artifacts.

## Follow-up Fix

- Tightened `backend/tests/integration/test_capability_skill_seeds.py::test_sci_capability_methodology_samples_are_parseable_and_specific` so `research_question_to_paper` now explicitly requires `manuscript_draft` alongside the other paper-build artifacts.
- This protects the Task 2 manuscript contract: if the seed ever drops `manuscript_draft`, the required-artifacts subset assertion will fail.

### Verification

```bash
cd backend && .venv/bin/python -m pytest tests/integration/test_capability_skill_seeds.py::test_sci_capability_methodology_samples_are_parseable_and_specific -v
```

Output:

- `PASSED [100%]`
