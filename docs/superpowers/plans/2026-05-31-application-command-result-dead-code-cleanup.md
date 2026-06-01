# Application Command/Result Dead-Code Cleanup Plan

**Goal:** Complete one Phase 6 cleanup batch by removing retired application command/result contracts that have no runtime, test, or documentation references outside the guard.

**Scope:** Backend application contracts only. This batch does not change runtime behavior, API response shapes, or frontend code.

## Tasks

- [x] Verify with `rg` that `FeatureLaunchCommand`, `FeatureLaunchResult`, `ThesisStatusResult`, `ThesisPreviewResult`, `ThesisCancelResult`, and `application.commands` have no live references.
- [x] Add an architecture guard preventing those retired contracts from returning.
- [x] Watch the guard fail before deletion.
- [x] Delete `backend/src/application/commands.py`.
- [x] Remove retired result dataclasses from `backend/src/application/results.py`.
- [x] Re-run the guard, feature execution contract tests, and ruff on touched backend files.

## Verification

```bash
rg -n "FeatureLaunchCommand|FeatureLaunchResult|ThesisStatusResult|ThesisPreviewResult|ThesisCancelResult|application\\.commands" backend/src backend/tests docs -g '*.py' -g '*.md' -g '!backend/tests/architecture/test_dataservice_boundaries.py'
cd backend && .venv/bin/python -m pytest tests/architecture/test_dataservice_boundaries.py::test_retired_application_command_result_contracts_are_removed tests/architecture/test_feature_execution_contract.py -q
cd backend && .venv/bin/ruff check src/application/results.py tests/architecture/test_dataservice_boundaries.py
```
