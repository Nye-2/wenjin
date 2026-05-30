# Workspace Reference Library

更新时间：2026-05-28
状态：Current

本文档是 workspace 文献中心的当前事实源。历史重建任务书、SSOT review 和阶段性计划已清理；追溯请使用 Git 历史。

## 1. 定位

Workspace Reference Library 是 workspace 级文献与证据的用户入口；canonical 数据事实源已经收敛到 DataService Source/Provenance/Asset 域。

所有文献来源统一进入 `sources`；gateway 层的 reference routes 只是产品入口命名，运行时不再通过 legacy reference tables 写入事实数据：

- 上传 PDF
- Semantic Scholar 检索
- deep search / deep research 产物
- 手动录入
- BibTeX import

所有后续功能统一读取 Source DataService；gateway references router、BibTeX export/validation 和 Prism `refs.bib` sync 均不得注入 runtime DB session：

- 文献中心 UI
- outline-first page index / text unit 检索
- writing evidence pack
- citation key
- `refs.bib` projection
- workspace Prism pending changes
- Prism source links / context rail
- LaTeX citation validation
- usage trace

## 2. 事实源不变量

1. 文献中心唯一事实源是 canonical `sources`；legacy `workspace_references*` / `reference_*` 不再承载运行时 import、detail、preprocess 或 usage 逻辑，并由 migration `072_drop_legacy_reference_tables.py` 删除。
2. 所有文献资产必须绑定 `workspace_id`，workspace 间不共享全文、索引、状态或 citation key。
3. citation key 由系统生成并在 workspace 内唯一，LLM 只能使用已有 key。
4. Semantic Scholar 的 `verified_papers` 是检索导入事实来源；`model_synthesis` 和 `unverified_leads` 只能作为分析或下一轮检索线索。
5. 上传全文进入 `workspace_assets` / `source_assets`，预处理后写入 canonical `source_outline_nodes` 和 `source_text_units`。
6. 写作 evidence pack 只从已纳入 Reference Library 的文献和索引内容构建。
7. `refs.bib` 是 projection，由 `SourceBibliographyService` 从 Source DataService metadata 生成。
8. Prism 写入正文引用时必须同步或校验 `refs.bib`；agent 不直接手写 `refs.bib` 内容。
9. capability 通过 `citation_policy` 声明 Library citation contract；SCI 主稿写作使用 `workspace_library` source scope，missing key 以 `block_prism_stage` 处理。
10. compile 前必须校验 `\cite{}` 是否存在于当前 workspace 文献中心。
11. Prism 稿件变更与文献/文档来源的关联进入 canonical `provenance_links`。

## 3. 数据模型

核心表：

- `sources`：文献主表，包含 title/authors/year/venue/doi/source/status/citation_key/read 状态等。
- `source_external_ids`：Semantic Scholar、上传 hash 等外部来源 ID。
- `source_assets` + `workspace_assets`：PDF、Markdown、manifest 和补充资产，包含 preprocess 状态。
- `source_outline_nodes`：目录/页码索引节点。
- `source_text_units`：可检索全文单元。
- `provenance_links`：引用、证据、Prism 变更、文档来源与写作使用审计。
- `source_bibtex_snapshots`：`refs.bib` projection 快照；运行时内容从 Source metadata 生成。
- `workspace_references*` / `reference_*`：legacy physical tables；migration `072_drop_legacy_reference_tables.py` 删除，ORM 模型已移除。

关键枚举：

- `source_type`: `upload | semantic_scholar | deep_search | manual | bibtex`
- `library_status`: `candidate | included | core | excluded | used_in_draft`
- `evidence_level`: `metadata_only | external_verified | uploaded_fulltext | indexed_fulltext`
- `fulltext_status`: `none | uploaded | preprocessing | indexed | failed`

## 4. 服务与 API

服务层：

- `SourceDataService`：CRUD、去重、citation key 唯一性、详情响应、evidence pack、citation usage。
- `SourceLibraryImportService`：Source Library import service；manual、Semantic Scholar、BibTeX、deep search artifact 和 PDF upload 均委托 Source/Asset DataService。
- `SourcePreprocessService`：PDF 预处理、Source outline/text units 写入。
- Source outline/text-unit APIs：outline-first 检索与 page/content 读取。
- `SourceBibliographyService`：BibTeX 生成、citation validation、Prism sync。
- `PrismReviewDataService`：从 canonical Prism review content 与 Source/Provenance 生成 source links。
- LeadAgentRuntime：读取 capability `citation_policy`，把 Library sources 注入为 `library_context` / `citation_context`，在 Prism staging 时阻断 missing citation key，并记录 `record_source_citation_usage`。

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
- 支持详情 Dialog，展示 metadata、abstract、BibTeX、assets、source history、preprocess summary、usage/provenance summary。
- 支持同步 `refs.bib` 到 workspace Prism。
- 支持从 Prism context rail 的 source link 回到文献/文档详情。

刷新约定：

- Reference 变更发布 `workspace.refresh`，`refresh_targets` 包含 `references`。
- 前端收到 refresh 后刷新 `useWorkspaceStore.references`。
- 详情 Dialog 以 `/references/{reference_id}` 返回的详情响应为准；列表只承载卡片级摘要。

## 6. 当前已完成

- Source/Provenance/Asset canonical tables 已落地，Reference Library gateway list/count/detail/update/delete/status/evidence pack 已走 Source DataService。
- API、服务、前端 LiteraturePanel、Agent tools、BibTeX/citation validation 已落地。
- Reference detail 已接入 Source detail、canonical assets、source history、preprocess summary 和 provenance usage。
- Reference PDF upload 直接创建 canonical `sources`、`workspace_assets`、`source_assets`，queued preprocess payload 使用 `source_id` / `source_asset_id` / `workspace_asset_id`。
- `sync_prism` 将 BibTeX projection 快照写入 canonical `source_bibtex_snapshots`，不再写 `reference_bibtex_snapshots`。
- Gateway import/BibTeX 服务已改成 Source 命名：`SourceLibraryImportService` / `SourceBibliographyService`，不再保留 legacy reference service class alias。
- Legacy `WorkspaceReferenceService`、`ReferencePreprocessService`、`ReferenceIndexService` 和 `ReferenceUsageService` 已从 runtime service surface 删除。
- Legacy reference ORM table models 已删除；`Reference*` enum 仅作为 API/status 校验类型保留。
- Prism context rail 已能展示 canonical source links，并 deep-link 回 Library / Documents。
- Release gate 覆盖 Semantic Scholar verified import、上传预处理、Reference writing workflow、Prism Review workflow、Reference Import Service、前端 action contract。
- Backend verification：`cd backend && .venv/bin/python -m pytest tests/ -q` 通过，`1938 passed`。

## 7. Workflow Gate

当前写作闭环的最小可回归路径是：

1. Reference Library 生成 outline-first evidence pack。
2. capability 声明 `citation_policy.source_scope=workspace_library`；Lead Agent 将 Library citation keys 作为写作唯一引用事实源。
3. 写作使用 citation key 通过 `SourceDataService.record_citation_usage` 写入 `provenance_links`，并把候选/已纳入 source 推进到 `used_in_draft`。
4. `SourceBibliographyService` 以当前 workspace 文献和 usage 生成 `refs.bib`。
5. `sync_prism` 将 `refs.bib` 写入 workspace Prism，并确保 `main.tex` 包含 bibliography 入口。
6. Prism review content 中可识别的 citation key 进入 `provenance_links`。
7. Prism staging 和 compile 前用 citation validation 阻断 missing key 和 metadata-only key。

对应门禁：`tests/services/test_reference_writing_workflow_gate.py`。

## 8. 后续增强

以下为体验增强，不阻塞当前主链路：

- usage event 跳转到对应 artifact、task、LaTeX project 或章节位置。
- source history 增加过滤和审计视图。
- preprocess 状态在详情 Dialog 中实时刷新。
- 显式 TaskReport source usage payload 可进一步补充 citation-derived source links。
