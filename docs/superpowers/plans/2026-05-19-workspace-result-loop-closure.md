# Workspace Result Loop Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current checkbox-first result flow with a preview-first workspace result loop that lets users read staged outputs, save selected outputs into rooms, and reopen committed results in room detail views.

**Architecture:** Keep the existing `TaskReport.outputs` contract as the staged source of truth, add room detail read endpoints on the backend, then introduce one shared frontend projection (`WorkspaceResultPreview`) that powers both execution completed cards and room detail panes. Commit remains execution-owned, but commit responses now return room focus metadata so the UI can deep-link into committed room items without ad hoc heuristics.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy async, Next.js 16, React 19, TypeScript, Vitest, Playwright

---

## File Structure

- Create: `frontend/lib/workspace-result-preview.ts`
- Create: `frontend/app/(workbench)/workspaces/[id]/components/result-preview/ResultPreviewList.tsx`
- Create: `frontend/app/(workbench)/workspaces/[id]/components/result-preview/ResultPreviewDetail.tsx`
- Create: `frontend/app/(workbench)/workspaces/[id]/components/result-preview/ResultPreviewRenderer.tsx`
- Create: `frontend/app/(workbench)/workspaces/[id]/components/result-preview/CommitActionBar.tsx`
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/CompletedView.tsx`
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/ResultCard.tsx`
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/rooms/DocumentsDrawer.tsx`
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/rooms/LibraryDrawer.tsx`
- Modify: `frontend/lib/api/v2/documents.ts`
- Modify: `frontend/lib/api/v2/library.ts`
- Modify: `frontend/tests/unit/v2/CompletedView.test.tsx`
- Modify: `frontend/tests/unit/v2/ResultCard.test.tsx`
- Modify: `frontend/tests/unit/v2/rooms/DocumentsDrawer.test.tsx`
- Modify: `frontend/tests/unit/v2/rooms/LibraryDrawer.test.tsx`
- Modify: `backend/src/gateway/routers/workspace_rooms.py`
- Modify: `backend/src/services/execution_commit_service.py`
- Modify: `backend/tests/gateway/routers/test_workspace_rooms_router.py`
- Modify: `backend/tests/services/test_execution_commit_service.py`

### Task 1: Backend Room Detail Endpoints

**Files:**
- Modify: `backend/tests/gateway/routers/test_workspace_rooms_router.py`
- Modify: `backend/src/gateway/routers/workspace_rooms.py`

- [ ] **Step 1: Write the failing router tests for document and library detail**

```python
def test_get_library_item_happy(self) -> None:
    app, client = _make_app()
    fake_item = _fake_row(id="lib-1", workspace_id=WS_ID, title="Paper A", abstract="Summary")

    with pytest.MonkeyPatch.context() as mp:
        mock_svc = MagicMock()
        mock_svc.get = AsyncMock(return_value=fake_item)
        mp.setattr(workspace_rooms, "_library_service", lambda db: mock_svc)
        resp = client.get(f"/workspaces/{WS_ID}/library/lib-1")

    assert resp.status_code == 200
    assert resp.json()["id"] == "lib-1"
    assert resp.json()["abstract"] == "Summary"


def test_get_document_happy(self) -> None:
    app, client = _make_app()
    fake_doc = _fake_row(
        id="doc-1",
        workspace_id=WS_ID,
        name="Outline",
        metadata_json={"content": "# Intro"},
    )

    with pytest.MonkeyPatch.context() as mp:
        mock_svc = MagicMock()
        mock_svc.get = AsyncMock(return_value=fake_doc)
        mp.setattr(workspace_rooms, "_documents_service", lambda db: mock_svc)
        resp = client.get(f"/workspaces/{WS_ID}/documents/doc-1")

    assert resp.status_code == 200
    assert resp.json()["id"] == "doc-1"
    assert resp.json()["metadata_json"]["content"] == "# Intro"
```

- [ ] **Step 2: Run the router tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/gateway/routers/test_workspace_rooms_router.py -k 'get_library_item_happy or get_document_happy' -q`

Expected: `404` or missing route failures for the new GET detail endpoints.

- [ ] **Step 3: Add minimal GET detail endpoints**

```python
@router.get("/{ws_id}/library/{item_id}")
async def get_library_item(...):
    await _assert_workspace_owner(ws_id, current_user, workspace_service)
    item = await _library_service(db).get(ws_id, item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Library item not found")
    return _row_to_dict(item)


@router.get("/{ws_id}/documents/{doc_id}")
async def get_document(...):
    await _assert_workspace_owner(ws_id, current_user, workspace_service)
    doc = await _documents_service(db).get(ws_id, doc_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return _row_to_dict(doc)
```

- [ ] **Step 4: Re-run the router tests**

Run: `cd backend && .venv/bin/python -m pytest tests/gateway/routers/test_workspace_rooms_router.py -k 'get_library_item_happy or get_document_happy' -q`

Expected: `2 passed`

### Task 2: Commit Response Room Targets

**Files:**
- Modify: `backend/tests/services/test_execution_commit_service.py`
- Modify: `backend/src/services/execution_commit_service.py`

- [ ] **Step 1: Write the failing commit response test**

```python
@pytest.mark.asyncio
async def test_commit_outputs_returns_room_targets_for_committed_items() -> None:
    execution = SimpleNamespace(
        id="exec-1",
        workspace_id="ws-1",
        user_id="user-1",
        feature_id="paper_outline",
        result={"task_report": SAMPLE_TASK_REPORT},
    )
    execution_service = MagicMock()
    execution_service.get_by_id = AsyncMock(return_value=execution)

    created_document = SimpleNamespace(id="doc-9")
    created_library = SimpleNamespace(id="lib-8")

    service = ExecutionCommitService(
        execution_service=execution_service,
        library_service=MagicMock(add=AsyncMock(return_value=created_library)),
        documents_service=MagicMock(add=AsyncMock(return_value=created_document)),
        decisions_service=MagicMock(),
        memory_service=MagicMock(),
        workspace_tasks_service=MagicMock(),
        run_history_service=MagicMock(record=AsyncMock()),
    )

    result = await service.commit_outputs("exec-1", accept_all=True)

    assert result["room_targets"] == {
        "documents": [{"output_id": "doc-output", "item_id": "doc-9"}],
        "library": [{"output_id": "paper-output", "item_id": "lib-8"}],
    }
```

- [ ] **Step 2: Run the commit service test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/services/test_execution_commit_service.py -k room_targets -q`

Expected: missing `room_targets` assertion failure.

- [ ] **Step 3: Add minimal room target collection to commit_outputs**

```python
room_targets: dict[str, list[dict[str, str]]] = {"documents": [], "library": []}

created_library = await self.library.add(...)
room_targets["library"].append({"output_id": output.id, "item_id": created_library.id})

created_document = await self.documents.add(...)
room_targets["documents"].append({"output_id": output.id, "item_id": created_document.id})

result: dict[str, Any] = {"committed": counts, "room_targets": room_targets}
```

- [ ] **Step 4: Re-run the commit service test**

Run: `cd backend && .venv/bin/python -m pytest tests/services/test_execution_commit_service.py -k room_targets -q`

Expected: `1 passed`

### Task 3: Shared Frontend Result Projection

**Files:**
- Create: `frontend/lib/workspace-result-preview.ts`
- Modify: `frontend/tests/unit/v2/CompletedView.test.tsx`

- [ ] **Step 1: Write the failing CompletedView test for preview-first rendering**

```tsx
it("shows preview rows and detail content for document outputs", () => {
  render(
    <CompletedView
      result={{
        task_report: {
          narrative: "Outline completed.",
          outputs: [
            {
              id: "doc-1",
              kind: "document",
              preview: "论文框架大纲",
              default_checked: true,
              data: {
                name: "outline.md",
                mime_type: "text/markdown",
                doc_kind: "outline",
                content: "# 第一章\\n- 背景",
              },
            },
          ],
        },
      }}
    />,
  );

  expect(screen.getByText("论文框架大纲")).toBeInTheDocument()
  expect(screen.getByText("# 第一章", { exact: false })).toBeInTheDocument()
  expect(screen.queryByText("View full result")).not.toBeInTheDocument()
})
```

- [ ] **Step 2: Run the CompletedView test to verify it fails**

Run: `cd frontend && npx vitest run tests/unit/v2/CompletedView.test.tsx -t 'shows preview rows and detail content for document outputs'`

Expected: no preview detail and/or raw JSON toggle still present.

- [ ] **Step 3: Add the shared projection helper**

```ts
export type WorkspaceResultPreview = {
  id: string;
  source: "staged_output" | "document_room" | "library_room";
  kind: "document" | "library_item" | "memory_fact" | "decision" | "task";
  title: string;
  subtitle: string | null;
  badge: string | null;
  previewMode: "markdown" | "plain_text" | "outline" | "citation" | "json_fallback";
  previewText: string | null;
  metadataLines: string[];
  defaultChecked: boolean;
  roomTarget?: { room: "documents" | "library"; itemId?: string | null; query?: string | null };
};
```

- [ ] **Step 4: Re-run the CompletedView test after wiring the helper into the next task**

Run: `cd frontend && npx vitest run tests/unit/v2/CompletedView.test.tsx -t 'shows preview rows and detail content for document outputs'`

Expected: still failing until the renderer lands, which is the correct red state for Task 4.

### Task 4: CompletedView Preview + Commit Review Surface

**Files:**
- Create: `frontend/app/(workbench)/workspaces/[id]/components/result-preview/ResultPreviewList.tsx`
- Create: `frontend/app/(workbench)/workspaces/[id]/components/result-preview/ResultPreviewDetail.tsx`
- Create: `frontend/app/(workbench)/workspaces/[id]/components/result-preview/ResultPreviewRenderer.tsx`
- Create: `frontend/app/(workbench)/workspaces/[id]/components/result-preview/CommitActionBar.tsx`
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/CompletedView.tsx`
- Modify: `frontend/tests/unit/v2/CompletedView.test.tsx`

- [ ] **Step 1: Expand the failing tests to cover selection and room actions**

```tsx
it("shows room links from next actions beside the preview detail", () => {
  render(
    <CompletedView
      workspaceId="ws-1"
      nextActions={[{ action: "open_artifact", artifact_kind: "document", item_id: "doc-1", title: "论文框架大纲" }]}
      result={{ task_report: { outputs: [{ id: "doc-1", kind: "document", preview: "论文框架大纲", data: { name: "outline.md", mime_type: "text/markdown", doc_kind: "outline", content: "# 第一章" } }] } }}
    />,
  )

  expect(screen.getByRole("link", { name: "查看产物" })).toBeInTheDocument()
})
```

- [ ] **Step 2: Run the focused CompletedView suite and verify red**

Run: `cd frontend && npx vitest run tests/unit/v2/CompletedView.test.tsx`

Expected: at least one failure for missing preview/detail rendering or missing room link placement.

- [ ] **Step 3: Implement minimal preview-first CompletedView**

```tsx
const previews = buildWorkspaceResultPreviews({ result, workspaceId, nextActions })
const [selectedId, setSelectedId] = useState(previews[0]?.id ?? null)

return (
  <div>
    <ResultPreviewList previews={previews} selectedId={selectedId} onSelect={setSelectedId} />
    <ResultPreviewDetail preview={selectedPreview} />
    <CommitActionBar mode="execution" />
  </div>
)
```

- [ ] **Step 4: Re-run CompletedView tests**

Run: `cd frontend && npx vitest run tests/unit/v2/CompletedView.test.tsx`

Expected: `passed`

### Task 5: ResultCard Preview-first Save Flow

**Files:**
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/ResultCard.tsx`
- Modify: `frontend/tests/unit/v2/ResultCard.test.tsx`

- [ ] **Step 1: Write the failing ResultCard test for preview toggle and saved state**

```tsx
it("expands staged previews before saving to workspace", async () => {
  render(<ResultCard data={SAMPLE_DATA} />)

  fireEvent.click(screen.getByText("查看结果"))

  expect(screen.getByText("Deep Learning")).toBeInTheDocument()
  expect(screen.getByText("保存到工作区")).toBeInTheDocument()
})
```

- [ ] **Step 2: Run the focused ResultCard suite and verify red**

Run: `cd frontend && npx vitest run tests/unit/v2/ResultCard.test.tsx -t 'expands staged previews before saving to workspace'`

Expected: button or preview content missing.

- [ ] **Step 3: Implement the minimal ResultCard changes**

```tsx
const [expanded, setExpanded] = useState(false)
const previews = buildWorkspaceResultPreviews({ resultCardData: data })

<button onClick={() => setExpanded((prev) => !prev)}>
  {expanded ? "收起结果" : "查看结果"}
</button>
{expanded ? <ResultPreviewList ... /> : null}
<CommitActionBar commitLabel="保存到工作区" ... />
```

- [ ] **Step 4: Re-run ResultCard tests**

Run: `cd frontend && npx vitest run tests/unit/v2/ResultCard.test.tsx`

Expected: `passed`

### Task 6: Documents and Library Split View

**Files:**
- Modify: `frontend/lib/api/v2/documents.ts`
- Modify: `frontend/lib/api/v2/library.ts`
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/rooms/DocumentsDrawer.tsx`
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/rooms/LibraryDrawer.tsx`
- Modify: `frontend/tests/unit/v2/rooms/DocumentsDrawer.test.tsx`
- Modify: `frontend/tests/unit/v2/rooms/LibraryDrawer.test.tsx`

- [ ] **Step 1: Write the failing drawer detail tests**

```tsx
it("shows the selected document preview in a detail pane", async () => {
  global.fetch = vi.fn()
    .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(MOCK_ITEMS) })
    .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({ id: "doc-2", name: "Literature Review Outline", mime_type: "text/markdown", doc_kind: "outline", metadata_json: { content: "# Outline" } }) })

  render(<DocumentsDrawer workspaceId="ws-1" open={true} onClose={vi.fn()} focusItemId="doc-2" />)

  await screen.findByText("# Outline", { exact: false })
})
```

- [ ] **Step 2: Run the drawer suites and verify red**

Run: `cd frontend && npx vitest run tests/unit/v2/rooms/DocumentsDrawer.test.tsx tests/unit/v2/rooms/LibraryDrawer.test.tsx`

Expected: detail pane assertions fail.

- [ ] **Step 3: Add detail API calls and split-view rendering**

```ts
export async function getDocument(workspaceId: string, docId: string): Promise<DocumentDetail> { ... }
export async function getLibraryItem(workspaceId: string, itemId: string): Promise<LibraryItemDetail> { ... }
```

```tsx
const [selectedId, setSelectedId] = useState(focusItemId ?? null)
const [detail, setDetail] = useState<DocumentDetail | null>(null)

useEffect(() => {
  if (!selectedId) return
  void getDocument(workspaceId, selectedId).then(setDetail)
}, [workspaceId, selectedId])
```

- [ ] **Step 4: Re-run drawer suites**

Run: `cd frontend && npx vitest run tests/unit/v2/rooms/DocumentsDrawer.test.tsx tests/unit/v2/rooms/LibraryDrawer.test.tsx`

Expected: `passed`

### Task 7: Final Verification

**Files:**
- No code changes expected

- [ ] **Step 1: Run backend targeted verification**

Run: `cd backend && .venv/bin/python -m pytest tests/gateway/routers/test_workspace_rooms_router.py tests/services/test_execution_commit_service.py -q`

Expected: all targeted backend tests pass.

- [ ] **Step 2: Run frontend targeted verification**

Run: `cd frontend && npx vitest run tests/unit/v2/CompletedView.test.tsx tests/unit/v2/ResultCard.test.tsx tests/unit/v2/rooms/DocumentsDrawer.test.tsx tests/unit/v2/rooms/LibraryDrawer.test.tsx`

Expected: all targeted frontend tests pass.

- [ ] **Step 3: Run typecheck**

Run: `cd frontend && npm run typecheck`

Expected: `passed`

- [ ] **Step 4: Run browser regression on the workspace surface**

Run: `cd frontend && npx playwright test tests/e2e/error-severity.spec.ts tests/e2e/golden-path.spec.ts tests/e2e/iteration.spec.ts`

Expected: `passed`
