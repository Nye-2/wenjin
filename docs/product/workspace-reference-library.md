# Workspace Reference Library

更新时间：2026-05-06
状态：Current

本文档是 workspace 文献中心的当前事实源。历史重建任务书、SSOT review 和阶段性计划已清理；追溯请使用 Git 历史。

## 1. 定位

Workspace Reference Library 是 workspace 级文献与证据的单一事实源。

所有文献来源统一进入 `workspace_references`：

- 上传 PDF
- Semantic Scholar 检索
- deep search / deep research 产物
- 手动录入
- BibTeX import

所有后续功能统一读取 Reference Library：

- 文献中心 UI
- outline-first page index / text unit 检索
- writing evidence pack
- citation key
- `refs.bib` projection
- WenjinPrism pending changes
- LaTeX citation validation
- usage trace

## 2. 事实源不变量

1. 文献中心唯一事实源是 `workspace_references`。
2. 所有文献资产必须绑定 `workspace_id`，workspace 间不共享全文、索引、状态或 citation key。
3. citation key 由系统生成并在 workspace 内唯一，LLM 只能使用已有 key。
4. Semantic Scholar 的 `verified_papers` 是检索导入事实来源；`model_synthesis` 和 `unverified_leads` 只能作为分析或下一轮检索线索。
5. 上传全文进入 `reference_assets`，预处理后写入 `reference_outline_nodes` 和 `reference_text_units`。
6. 写作 evidence pack 只从已纳入 Reference Library 的文献和索引内容构建。
7. `refs.bib` 是 projection，由 `ReferenceBibTeXService` 从 `workspace_references` 生成。
8. Prism 写入正文引用时必须同步或校验 `refs.bib`。
9. compile 前必须校验 `\cite{}` 是否存在于当前 workspace 文献中心。

## 3. 数据模型

核心表：

- `workspace_references`：文献主表，包含 title/authors/year/venue/doi/source/status/citation_key/read 状态等。
- `reference_external_ids`：Semantic Scholar 等外部来源 ID。
- `reference_assets`：PDF、Markdown、manifest 和补充资产，包含 preprocess 状态。
- `reference_outline_nodes`：目录/页码索引节点。
- `reference_text_units`：可检索全文单元。
- `reference_usage_events`：引用、证据和写作使用审计。
- `reference_bibtex_snapshots`：`refs.bib` projection 快照。

关键枚举：

- `source_type`: `upload | semantic_scholar | deep_search | manual | bibtex`
- `library_status`: `candidate | included | core | excluded | used_in_draft`
- `evidence_level`: `metadata_only | external_verified | uploaded_fulltext | indexed_fulltext`
- `fulltext_status`: `none | uploaded | preprocessing | indexed | failed`

## 4. 服务与 API

服务层：

- `WorkspaceReferenceService`：CRUD、去重、citation key 唯一性、详情响应。
- `ReferenceImportService`：Semantic Scholar、BibTeX、deep search artifact、manual、PDF upload 导入。
- `ReferencePreprocessService`：PDF 预处理、outline/text units 写入。
- `ReferenceIndexService`：outline-first 检索与 page/content 读取。
- `ReferenceEvidenceService`：writing evidence pack。
- `ReferenceUsageService`：记录引用和证据使用。
- `ReferenceBibTeXService`：BibTeX 生成、citation validation、Prism sync。

API 面：

- `GET /api/workspaces/{workspace_id}/references`
- `GET /api/workspaces/{workspace_id}/references/{reference_id}`
- `POST /api/workspaces/{workspace_id}/references/manual`
- `POST /api/workspaces/{workspace_id}/references/upload`
- `POST /api/workspaces/{workspace_id}/references/import/semantic-scholar`
- `POST /api/workspaces/{workspace_id}/references/import/deep-search-artifact`
- `POST /api/workspaces/{workspace_id}/references/import/bibtex`
- `GET /api/workspaces/{workspace_id}/references/{reference_id}/outline`
- `GET /api/workspaces/{workspace_id}/references/{reference_id}/outline/{node_id}/content`
- `GET /api/workspaces/{workspace_id}/references/{reference_id}/pages`
- `POST /api/workspaces/{workspace_id}/references/search-text-units`
- `POST /api/workspaces/{workspace_id}/references/evidence-pack`
- `GET /api/workspaces/{workspace_id}/references/bibtex`
- `POST /api/workspaces/{workspace_id}/references/bibtex/validate`
- `POST /api/workspaces/{workspace_id}/references/bibtex/sync-prism`

## 5. 前端行为

`LiteraturePanel` 是当前 Reference Library UI：

- 展示统计、筛选、文献卡片、状态 badge、citation key、DOI。
- 支持 PDF 上传，上传后显示 preprocess pending/running/succeeded/failed。
- 支持目录展开，读取 reference outline。
- 支持详情 Dialog，展示 metadata、abstract、BibTeX、assets、source history、preprocess summary、recent usage events。
- 支持同步 `refs.bib` 到 WenjinPrism。

刷新约定：

- Reference 变更发布 `workspace.refresh`，`refresh_targets` 包含 `references`。
- 前端收到 refresh 后刷新 `useWorkspaceStore.references`。
- 详情 Dialog 以 `/references/{reference_id}` 返回的详情响应为准；列表只承载卡片级摘要。

## 6. 当前已完成

- 7 张 Reference Library 数据表已落地。
- API、服务、前端 LiteraturePanel、Agent tools、BibTeX/citation validation 已落地。
- Reference detail 已接入 source history、preprocess summary 和 usage events。
- Release gate 覆盖 Semantic Scholar verified import、上传预处理、Reference writing workflow、Prism Review workflow、Reference Import Service、前端 action contract。

## 7. Workflow Gate

当前写作闭环的最小可回归路径是：

1. Reference Library 生成 outline-first evidence pack。
2. 写作使用 citation key 记录 `reference_usage_events`，并把候选/已纳入文献推进到 `used_in_draft`。
3. `ReferenceBibTeXService` 以当前 workspace 文献和 usage 生成 `refs.bib`。
4. `sync_prism` 将 `refs.bib` 写入 WenjinPrism，并确保 `main.tex` 包含 bibliography 入口。
5. compile 前用 citation validation 阻断 missing key 和 metadata-only key。

对应门禁：`tests/services/test_reference_writing_workflow_gate.py`。

## 8. 后续增强

以下为体验增强，不阻塞当前主链路：

- usage event 跳转到对应 artifact、task、LaTeX project 或章节位置。
- source history 增加过滤和审计视图。
- preprocess 状态在详情 Dialog 中实时刷新。
