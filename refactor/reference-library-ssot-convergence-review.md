# Reference Library SSOT 收敛 Review

更新时间：2026-04-30
状态：Closed / implementation verified（2026-05-06 复验通过）
适用范围：`/home/cjz/wenjin`

> **复验记录（2026-05-06）**
> - 静态扫描：旧 `WorkspacePaper/WorkspaceLiterature/BibTeXExporter` 无残留
> - bypass tool deny-list：单源化正常（`REFERENCE_LIBRARY_BYPASS_TOOL_NAMES`）
> - Targeted tests：56 passed
> - Full verification：2067 passed
> - mypy：0 errors (402 files)

本文记录 2026-04-30 对 Reference Library 重构后的 SSOT 收敛审查结果和收尾修复结果。它不是初始设计任务书，而是当前实现状态、架构边界、已修复问题和后续防回归约束的工程交接文档。

## 1. Review 结论

当前 Reference Library 主链路已经收敛：

```text
Semantic Scholar / Deep Research / PDF Upload / BibTeX / Manual
  -> ReferenceImportService
  -> workspace_references
  -> reference_assets / outline_nodes / text_units
  -> Reference Library UI / agent tools / BibTeX / Prism
```

旧 `Paper / WorkspacePaper / WorkspaceLiterature` 作为文献中心事实源的路径已经从可执行 API 和主 agent 工具路径中移除。SCI `literature_search` 和 thesis `deep_research` 已经以 Semantic Scholar 为检索源，并把 verified papers 导入 Reference Library。BibTeX 也已经以 Reference Library 为唯一 projection 源。

本轮 review 发现的剩余边界问题已经修复并通过后端全量测试。修复覆盖：

1. workspace-scoped 工具强约束下沉到工具层。
2. 禁止绕过 Reference Library 的外部检索工具 deny-list 单源化。
3. page-index 页码读取改为区间重叠匹配。
4. 写作期 `reference_usage_events` 扩展为引用/证据使用事实源。
5. 本地 academic MCP 工具中的非 SSOT academic discovery 语义被移除。

因此当前状态应定义为：

```text
主链路收敛：已完成
边界收敛：已完成
SSOT 严格闭环：已完成
```

本轮验证：

```bash
cd /home/cjz/wenjin/backend
uv run pytest -q
# 2034 passed, 3 skipped

uv run ruff check src tests --output-format=concise
# All checks passed

uv run python -m compileall src
# passed
```

## 2. 当前目标架构

### 2.1 单一事实源

Reference Library 的唯一主表是：

```text
workspace_references
```

一行代表一个 workspace 内的一篇文献。文献不做全局共享事实源，`workspace_id` 是隔离边界。跨 workspace 可以有同一 DOI 或标题，但状态、citation key、全文资产、阅读状态、使用记录必须互相隔离。

相关表职责：

| 表 | 职责 |
|---|---|
| `workspace_references` | workspace 内文献主记录、metadata、citation key、状态 |
| `reference_external_ids` | Semantic Scholar paperId、upload hash 等外部/来源 ID |
| `reference_assets` | PDF、Markdown、manifest、补充文件资产 |
| `reference_outline_nodes` | 目录和章节索引，支持 page index / outline-first 读取 |
| `reference_text_units` | 可读文本单元，支持章节、页码、全文片段检索 |
| `reference_usage_events` | 写作期引用和证据使用记录 |
| `reference_bibtex_snapshots` | `refs.bib` projection 快照 |

### 2.2 文献进入路径

所有文献进入 Reference Library：

```text
PDF Upload
  -> ReferenceImportService.import_uploaded_pdf
  -> workspace_references + reference_assets
  -> ReferencePreprocessService
  -> outline_nodes + text_units

Semantic Scholar Query
  -> LiteratureSearchService.search
  -> verified_papers
  -> ReferenceImportService.import_semantic_scholar_papers
  -> workspace_references

Deep Research
  -> Semantic Scholar verified discovery
  -> ReferenceImportService.import_semantic_scholar_papers
  -> workspace_references

BibTeX
  -> BibTeXParser
  -> ReferenceImportService.import_bibtex
  -> workspace_references

Manual
  -> ReferenceImportService.import_manual
  -> workspace_references
```

不得出现以下入口重新成为事实源：

```text
Paper
WorkspacePaper
WorkspaceLiterature
PaperService
/api/papers*
/api/workspaces/{workspace_id}/literature*
direct semantic_scholar_search tool
direct search_external tool
direct arxiv/pubmed/doi MCP academic tools in agent/subagent runtime
BibTeXExporter
```

### 2.3 调研路径

调研功能的事实边界：

```text
用户请求调研
  -> Compute feature
  -> LiteratureSearchService
  -> Semantic Scholar metadata
  -> verified_papers
  -> ReferenceImportService
  -> Reference Library
  -> LLM synthesis over verified_papers
```

LLM 只允许在已验证文献上做综合，不允许新增论文条目。输出结构应保持：

```text
verified_papers      # Semantic Scholar 可验证条目
model_synthesis      # LLM 基于 verified_papers 的综合
unverified_leads     # 下一轮关键词、方向或待检索线索，不是论文引用
reference_import     # 导入 Reference Library 的结果
```

### 2.4 Page Index / Outline-First 读取

用户提出的 page index 方向是正确的，当前实现目标是：

```text
模型先看 Reference Library 总目录
  -> 决定需要读哪些 reference / section / page
  -> 使用 Reference Library 工具读取章节或页码
  -> 再支持写作、对比、综述、方法引用
```

这不是向量 RAG。关键设计点：

1. `list_workspace_reference_outline` 给模型 workspace 级目录视图。
2. `search_workspace_references` 做轻量关键词匹配，不是语义向量召回。
3. `read_workspace_reference_section` 读取模型选中的章节。
4. page 读取 API 支持按页码范围读取 `reference_text_units`。
5. 模型必须先看目录再读取内容，避免 blind search。

### 2.5 BibTeX / Prism

BibTeX 不再由旧 exporter 生成。当前唯一 projection：

```text
ReferenceBibTeXService.build_bibtex
ReferenceBibTeXService.sync_prism
```

目标闭环：

```text
workspace_references
  -> citation_key
  -> refs.bib
  -> Prism project
  -> main.tex citations
  -> compile validation
  -> reference_usage_events
```

`refs.bib` 是 projection，不是主数据。主数据只能回写到 `workspace_references`。

## 3. 已完成收敛项

| 范围 | 当前状态 | 说明 |
|---|---|---|
| 数据模型 | 已完成主迁移 | `028_reference_library_rebuild.py` 创建 Reference Library 表并删除旧 paper/literature 表 |
| 旧 API | 已移除主入口 | `papers.py`、`literature.py` 不再作为 gateway router 暴露 |
| 前端文献中心 | 已迁移到 references API | 前端调用 `/workspaces/{workspace_id}/references*` |
| 文献上传 | 已迁移 | `kind=literature` 上传进入 Reference Library，不再写 thread-local PDF 作为事实源 |
| 大文件预处理 | 已接入 Reference Library | `reference_preprocess` 路径会生成 markdown/manifest 并更新 reference asset/index |
| SCI 文献检索 | 已收敛到 Semantic Scholar | `LiteratureSearchService` 返回 verified papers，SCI service 做 grounded synthesis |
| Thesis deep research | 已接入 Semantic Scholar + Reference Library | deep research 检索结果导入 Reference Library |
| Lead Agent 工具池 | 已过滤直接外检索工具 | `get_available_tools()` 不暴露 direct academic search tools |
| Subagent prompts | 已改为 Reference Library 读取 | Scout/Librarian 等提示不再要求 direct external search |
| BibTeX | 已迁移到 ReferenceBibTeXService | 旧 `BibTeXExporter` 删除 |
| Architecture guards | 已新增 | 防止旧 direct academic tools 和旧 exporter 回流 |

本轮已执行的后端验证：

```bash
cd /home/cjz/wenjin/backend
uv run pytest -q
# 2034 passed, 3 skipped

uv run ruff check src tests --output-format=concise
# All checks passed

uv run python -m compileall src
# passed
```

最近一次针对本 review 的局部验证：

```bash
cd /home/cjz/wenjin/backend
uv run pytest \
  tests/tools/test_reference_builtins.py \
  tests/subagents/test_graph_academic.py \
  tests/services/test_reference_index_service.py \
  tests/services/test_reference_usage_service.py \
  tests/agents/lead_agent/test_tools.py \
  tests/subagents/academic/test_resolver.py \
  tests/architecture/test_layer_boundaries.py \
  tests/integration/test_tool_chain.py \
  -q
```

结果：

```text
62 passed
```

## 4. 已修复问题

### RL-SSOT-001：Reference Library 工具仍可被显式 `workspace_id` 覆盖

严重级别：High
修复状态：已修复

Review 时现象：

`list_workspace_reference_outline`、`search_workspace_references`、`read_workspace_reference_section` 当前优先使用工具入参里的 `workspace_id`，其次才读 runtime config。

相关文件：

```text
backend/src/tools/builtins/references.py
backend/src/agents/middlewares/workspace_context.py
backend/src/subagents/graph.py
```

风险：

1. Lead Agent 路径有 `WorkspaceContextMiddleware.before_tool` 覆盖 workspace，但工具层本身不强制。
2. Subagent graph 当前只挂 execution middleware，没有挂 workspace-scoped guard。
3. 如果模型或测试注入了其他 workspace_id，subagent 可能读取非当前 workspace 文献。
4. 这会破坏 workspace 级文献隔离，也破坏 Reference Library SSOT 的安全边界。

已落地修复：

1. 在 `src.tools.builtins.references` 下沉统一解析逻辑。
2. runtime config 的 `workspace_id` 必须优先于工具参数。
3. 如果工具参数 `workspace_id` 与 runtime `workspace_id` 不一致，直接返回 `workspace_scope_violation`，不要静默覆盖。
4. subagent graph 增加 workspace-scoped middleware 或等价 guard。
5. 增加单元测试覆盖 Lead Agent 和 subagent 两条路径。

验收标准：

1. 工具参数传入其他 workspace_id 时不能读取数据。
2. subagent 调用 reference tools 时必须使用 runtime workspace。
3. `tests/tools/test_reference_builtins.py` 覆盖 mismatch case。
4. `tests/subagents/*` 覆盖 subagent reference tool runtime workspace injection。

### RL-SSOT-002：外检索 deny-list 还没有单源化

严重级别：Medium
修复状态：已修复

Review 时现象：

Lead Agent 有 `_REFERENCE_LIBRARY_BYPASS_TOOL_NAMES`，但 `AcademicAgentResolver` 有另一套 `_RETIRED_ACADEMIC_SEARCH_TOOLS`，内容不完全一致。

相关文件：

```text
backend/src/agents/lead_agent/agent.py
backend/src/subagents/academic/resolver.py
backend/tests/architecture/test_layer_boundaries.py
```

风险：

1. Lead Agent 默认路径已过滤，但 resolver 是公开导出的扩展路径。
2. 如果 resolver 被注入 `pubmed_search`、`doi_resolve`、`search_external`、`semantic_scholar_search`，当前逻辑可能放行。
3. 未来新增 MCP/tool 时容易漏掉一个过滤点。

已落地修复：

1. 新增共享常量模块，例如：

```text
backend/src/reference_library/boundaries.py
```

或放在更合适的现有模块中：

```text
backend/src/academic/literature/boundaries.py
```

2. 导出：

```python
REFERENCE_LIBRARY_BYPASS_TOOL_NAMES = frozenset({
    "semantic_scholar_search",
    "semantic_scholar_search_tool",
    "search_external",
    "get_paper_by_doi",
    "arxiv_search",
    "pubmed_search",
    "doi_resolve",
    "web_search",
    "crossref_search",
    "openalex_search",
})
```

3. Lead Agent、AcademicAgentResolver、architecture tests 全部引用同一个常量。
4. 禁止在多个文件手写各自 deny-list。

验收标准：

1. `get_available_tools(include_mcp=True)` 不暴露 bypass tools。
2. `AcademicAgentResolver` 的 requested/default 工具合并均过滤同一套 bypass tools。
3. architecture test 检查不能出现第二套硬编码列表。

### RL-SSOT-003：Page index 页码读取存在区间匹配 bug

严重级别：Medium
修复状态：已修复

Review 时现象：

`ReferenceIndexService.read_pages()` 以 `ReferenceTextUnit.page_start` 判断是否落在请求区间内：

```text
page_start >= request.page_start
page_start <= request.page_end
```

相关文件：

```text
backend/src/services/references/service.py
backend/src/gateway/routers/references.py
```

风险：

如果一个 text unit 覆盖第 3-5 页，用户请求第 4 页，当前逻辑会漏掉，因为 `unit.page_start=3 < request.page_start=4`。

这会直接影响 page index 的用户体验：模型按目录判断某段内容在某页附近，但 API 返回空，造成“索引里有内容却读不到”。

已落地修复：

按区间重叠读取：

```text
unit.page_start <= requested_page_end
and coalesce(unit.page_end, unit.page_start) >= requested_page_start
```

同时需要排除 `page_start is null` 的 unit，或者定义 null page 的 fallback 行为。

验收标准：

1. page unit 覆盖 3-5，查询 4-4 能返回。
2. 查询 1-2 不返回 3-5。
3. 查询 5-6 能返回 3-5。
4. 测试覆盖 `page_end is null` 的兼容情况。

### RL-SSOT-004：`reference_usage_events` 还不是完整写作链路事实源

严重级别：Medium
修复状态：已修复

Review 时现象：

引用使用记录主要依赖 `CitationContextMiddleware.after_model` 从最后一条 AI message 中解析 citation，再调用 `record_reference_usage`。

相关文件：

```text
backend/src/agents/middlewares/citation_context.py
backend/src/services/references/service.py
backend/src/task/workspace_feature_runtime.py
backend/src/tools/builtins/references.py
```

风险：

1. subagent 输出不一定经过同样的 citation after_model 记录。
2. Compute feature 写作产物落库时，没有统一解析 `\cite{}` 并确认 usage。
3. `read_workspace_reference_section` 读取了哪些 reference/section 没有记录。
4. `USED_IN_DRAFT` 和 `reference_usage_events` 不能完整表示哪些文献实际支撑了写作。
5. `used_only` BibTeX scope 和未来引用审计会漏数据。

已落地修复：

分两层记录：

```text
read/reference evidence access
  -> usage_type=background/comparison/method_support
  -> accepted_status=pending

draft citation materialization
  -> parse citation_key / \cite{}
  -> usage_type=citation_only or stronger semantic type
  -> accepted_status=pending/accepted
```

具体任务：

1. `read_workspace_reference_section` 成功读取时可记录一次 evidence access。
2. 写作类 feature finalize 时解析产物里的 citation key，调用 `ReferenceUsageService.record_usage`。
3. Prism apply 或 compile validation 后，把实际进入 manuscript 的 citation 标记为 accepted。
4. Citation middleware 保留为 chat 辅助记录，但不能作为唯一 usage 入口。

验收标准：

1. reference section 被读取后能在 `reference_usage_events` 找到记录。
2. feature artifact 包含 `\cite{key}` 时能关联到对应 `WorkspaceReference`。
3. Prism apply 后能把进入稿件的 citation usage 标记为 accepted 或 used_in_draft。
4. `ReferenceBibTeXService(scope=used_only)` 基于 usage event 能生成完整 `refs.bib`。

### RL-SSOT-005：本地 academic MCP 工具实现仍是产品语义残留

严重级别：Low
修复状态：已修复

Review 时现象：

以下本地 MCP academic tools 仍存在：

```text
backend/src/mcp/tools/arxiv.py
backend/src/mcp/tools/pubmed.py
backend/src/mcp/tools/doi.py
backend/src/mcp/tools/__init__.py
backend/tests/mcp/test_academic_tools.py
backend/tests/integration/test_tool_chain.py
```

当前 Lead Agent 已过滤 `arxiv_search/pubmed_search/doi_resolve`，所以主 agent 工具池不暴露它们。

风险：

1. 代码语义仍然表达“系统内置外部学术检索工具”。
2. 后续 agent 或 MCP 管理入口可能误接入。
3. 与“只用 Semantic Scholar，并且所有发现都进入 Reference Library”的收敛目标不一致。

已落地修复：

1. 删除这些本地 academic MCP tool 实现和相关测试。
2. 保留 MCP namespace，但不再表达 product academic discovery 工具。
3. architecture guard 禁止这些工具文件回归。

验收标准：

1. `rg "arxiv_search|pubmed_search|doi_resolve" backend/src` 只允许出现在共享 deny-list 和 guard tests 中。
2. `backend/src/mcp/tools` 不再表达 academic paper discovery 工具。
3. MCP framework 保留，但 product academic discovery 不走 MCP tools。

## 5. 已完成收尾任务

Task A-E 均已完成。以下任务描述保留为后续 review 和防回归检查的执行记录。

### Task A：Workspace-scoped reference tool hardening

目标：

把 workspace 隔离边界从 middleware 下沉到 reference built-in tools。

文件范围：

```text
backend/src/tools/builtins/references.py
backend/src/agents/middlewares/workspace_context.py
backend/src/subagents/graph.py
backend/tests/tools/test_reference_builtins.py
backend/tests/subagents/*
```

验收：

```bash
cd backend
uv run pytest tests/tools/test_reference_builtins.py tests/subagents -q
```

### Task B：Reference Library bypass tool deny-list 单源化

目标：

Lead Agent、AcademicAgentResolver、architecture tests 共用同一套禁止工具列表。

文件范围：

```text
backend/src/agents/lead_agent/agent.py
backend/src/subagents/academic/resolver.py
backend/tests/agents/lead_agent/test_tools.py
backend/tests/subagents/academic/test_resolver.py
backend/tests/architecture/test_layer_boundaries.py
```

验收：

```bash
cd backend
uv run pytest \
  tests/agents/lead_agent/test_tools.py \
  tests/subagents/academic/test_resolver.py \
  tests/architecture/test_layer_boundaries.py \
  -q
```

### Task C：Page index interval overlap 修复

目标：

修正 `read_pages()` 页码范围匹配，使跨页 text unit 不被漏召回。

文件范围：

```text
backend/src/services/references/service.py
backend/tests/services/test_reference_index_service.py
```

如果当前没有独立 `test_reference_index_service.py`，应新建。

验收：

```bash
cd backend
uv run pytest tests/services/test_reference_index_service.py -q
```

### Task D：Usage event 闭环

目标：

把 `reference_usage_events` 从 chat citation after-model 辅助记录，升级为写作期引用/证据使用事实源。

文件范围：

```text
backend/src/tools/builtins/references.py
backend/src/services/references/service.py
backend/src/task/workspace_feature_runtime.py
backend/src/agents/middlewares/citation_context.py
backend/tests/services/test_reference_usage_service.py
backend/tests/tools/test_reference_builtins.py
```

验收：

```bash
cd backend
uv run pytest \
  tests/services/test_reference_usage_service.py \
  tests/tools/test_reference_builtins.py \
  tests/agents/middlewares/test_citation_context.py \
  -q
```

### Task E：Academic MCP residue 清理

目标：

移除或隔离 `arxiv_search/pubmed_search/doi_resolve` 这类非 SSOT academic discovery 工具。

文件范围：

```text
backend/src/mcp/tools/arxiv.py
backend/src/mcp/tools/pubmed.py
backend/src/mcp/tools/doi.py
backend/src/mcp/tools/__init__.py
backend/tests/mcp/test_academic_tools.py
backend/tests/integration/test_tool_chain.py
backend/tests/architecture/test_layer_boundaries.py
```

验收：

```bash
cd backend
rg -n "arxiv_search|pubmed_search|doi_resolve" src tests
uv run pytest tests/architecture/test_layer_boundaries.py -q
```

允许残留位置必须限定为：

```text
shared deny-list
architecture guard forbidden string list
tests asserting forbidden tools are filtered
```

## 6. 最终 SSOT 验收标准

最终收敛完成后，应满足以下检查：

### 6.1 静态扫描

```bash
cd /home/cjz/wenjin

rg -n "WorkspacePaper|workspace_papers|WorkspaceLiterature|workspace_literature|PaperService|paper_service|routers\\.papers|routers\\.literature|/api/papers|/papers|/literature|BibTeXExporter|bibtex\\.exporter" \
  backend/src frontend/app frontend/components frontend/lib \
  -g '*.py' -g '*.ts' -g '*.tsx'

rg -n "semantic_scholar_search|semantic_scholar_search_tool|search_external|get_paper_by_doi|arxiv_search|pubmed_search|doi_resolve|crossref_search|openalex_search" \
  backend/src frontend/app frontend/components frontend/lib \
  -g '*.py' -g '*.ts' -g '*.tsx'
```

期望：

1. 第一组无可执行业务残留。
2. 第二组只允许出现在共享 deny-list、architecture guards、过滤测试中。

### 6.2 Backend targeted tests

```bash
cd backend
uv run pytest \
  tests/tools/test_reference_builtins.py \
  tests/services/test_reference_import_service.py \
  tests/services/test_reference_usage_service.py \
  tests/services/test_reference_index_service.py \
  tests/agents/lead_agent/test_tools.py \
  tests/subagents/academic/test_resolver.py \
  tests/agents/middlewares/test_citation_context.py \
  tests/architecture/test_layer_boundaries.py \
  -q
```

### 6.3 Full verification

```bash
cd backend && uv run pytest -q
cd backend && uv run ruff check src tests --output-format=concise
cd backend && uv run python -m compileall src
cd frontend && npm run typecheck
cd frontend && npm run lint
cd frontend && npm test
```

## 7. 架构不变量

后续任何实现不得破坏以下不变量：

1. Reference Library 的主数据只能是 `workspace_references`。
2. 文献检索只能通过 Compute feature / service 导入 Reference Library，不允许 agent 直接把外部检索结果当引用使用。
3. Semantic Scholar 是当前唯一外部文献检索源。
4. LLM 不能生成 verified paper，只能基于 verified papers 做 synthesis。
5. `unverified_leads` 只能是下一轮关键词、方向、作者群或检索式，不是论文引用。
6. `citation_key` 由系统生成并入库，LLM 只能引用已有 key。
7. `refs.bib` 是 projection，不是事实源。
8. workspace runtime identity 优先于所有工具入参。
9. subagent、Lead Agent、feature runtime 使用同一套 Reference Library 工具边界。
10. page index 读取必须按区间重叠召回，不能只看 `page_start`。
11. 写作产物进入 Prism 或 artifact 时，引用使用必须进入 `reference_usage_events`。
12. 旧 paper/literature API、模型、服务、工具不得重新作为兼容路径恢复。
