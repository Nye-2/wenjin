# Workspace Reference Library 重建工程任务书

更新时间：2026-04-30
状态：核心已实现（2026-05-06），少量扩展项待续
适用范围：`/home/cjz/wenjin`

> **完成度概要**
> - ✅ 7 张数据表（迁移 028）
> - ✅ 7 个服务类（WorkspaceReference / Import / Preprocess / Index / Evidence / Usage / BibTeX）
> - ✅ API 路由（Catalog / Import / Index / Evidence / BibTeX / 状态操作）
> - ✅ 前端 LiteraturePanel（统计、筛选、卡片、操作、目录查看、上传、详情 Dialog、BibTeX 预览）
> - ✅ Agent 工具命名对齐（list_reference_library / search_reference_text_units / read_reference_outline_node）
> - ✅ `validate_citations` LaTeX citation 校验工具
> - ⚠️ 详情 Drawer 完整功能：Usage events / Source history / Preprocess status 需后端 API 扩展

本文用于指导“文献中心”彻底重建。当前前提是：没有需要保留的历史真实数据，可以破坏性删除旧表、旧 API、旧服务和旧前端入口；不做双写、不做兼容层、不保留 fallback。目标是把文献中心从“上传 PDF 列表 + 调研导入列表”的双轨结构，重建为 workspace 级的统一证据库，支撑调研、page index、写作取证、BibTeX、Prism 和最终 LaTeX 编译。

## 1. 背景问题

当前系统存在两套文献事实源：

1. `Paper / WorkspacePaper / PaperSection / PaperChunk / PaperExtraction`
   - 主要服务上传 PDF、全文抽取、目录/章节检索。
   - 当前前端 `LiteraturePanel` 主要展示这套数据。
2. `WorkspaceLiterature`
   - 主要服务手动文献、deep research / Semantic Scholar 导入、写作服务读取文献 metadata、部分 BibTeX 生成。

这导致核心链路断裂：

```text
Semantic Scholar / deep search 发现文献
  -> 进入 WorkspaceLiterature
  -> 当前文献中心 UI 不完整可见
  -> page index 看不到
  -> BibTeX/citation key 不稳定

用户上传 PDF
  -> 进入 Paper / WorkspacePaper
  -> UI 可见
  -> 可做 section index
  -> 但和 deep search metadata 不在同一条文献资产线上
```

因此，本轮不是修补旧 `LiteratureService` 或 `Paper` API，而是重建统一文献中心：

```text
Workspace Reference Library
```

## 2. 总目标

建立单一事实源：

```text
workspace_references
```

所有文献来源统一进入：

```text
upload PDF
Semantic Scholar
deep search / deep research
manual
BibTeX import
```

所有后续功能统一读取：

```text
文献中心 UI
page index / outline-first evidence retrieval
写作 evidence pack
citation key
refs.bib
Prism pending changes
LaTeX compile citation validation
```

目标闭环：

```text
Discovery / Upload
  -> Workspace Reference Library
  -> Outline / Page Index
  -> Evidence Pack
  -> Writing with citation_key
  -> refs.bib projection
  -> Prism main.tex + refs.bib review
  -> Compile validation
  -> Usage trace
```

## 3. 非目标

本轮明确不做：

1. 不保留旧 `WorkspaceLiterature` 业务入口。
2. 不保留旧 `/papers` 作为文献中心入口。
3. 不做 `Paper` 与 `WorkspaceReference` 双写。
4. 不做旧数据兼容迁移的长期适配层。
5. 不引入向量数据库或 embedding 模型。
6. 不让 LLM 生成 citation key 或 BibTeX 主数据。
7. 不让 deep search 发现的文献自动变成 core，只进入 candidate。
8. 不让写作模型自由引用 evidence pack 之外的 citation key。

## 4. 架构原则

必须满足以下 invariant：

1. 文献中心唯一事实源是 `workspace_references`。
2. 所有文献资产必须带 `workspace_id`，workspace 间不共享全文、索引、状态和 citation key。
3. 全文文件只进入 `reference_assets`。
4. 模型先看目录，再决定读取章节/page；page index 是 outline-first，不是传统 RAG。
5. citation key 由系统生成并入库，LLM 只能使用。
6. `refs.bib` 是 projection，由 `ReferenceBibTeXService` 生成。
7. 写作只能引用 evidence pack 中出现的 `citation_key`。
8. Prism 写入正文引用时必须同步 `refs.bib`。
9. compile 前必须校验 `\cite{}` 是否存在于当前 workspace 文献中心。
10. 旧服务不得重新成为任何新链路的事实源。

## 5. 新数据模型

### 5.1 `workspace_references`

workspace 文献中心主表。一行代表一个 workspace 内的一篇文献。

字段：

```text
id                    uuid pk
workspace_id          varchar(36) not null index

title                 text not null
normalized_title      text not null
authors               jsonb not null default []
year                  int null
venue                 text null
publication_type      varchar(40) null
doi                   varchar(255) null
url                   text null
abstract              text null

source_type           varchar(40) not null
source_label          text null
source_run_id         varchar(36) null
source_artifact_id    varchar(36) null
verified_at           timestamptz null

library_status        varchar(30) not null default 'candidate'
evidence_level        varchar(40) not null default 'metadata_only'
fulltext_status       varchar(30) not null default 'none'

citation_key          varchar(120) not null
bibtex_entry_type     varchar(40) not null default 'article'
bibtex_fields         jsonb not null default {}

read_status           varchar(30) not null default 'unread'
tags                  jsonb not null default []
notes                 text null
is_deleted            boolean not null default false

created_at            timestamptz not null
updated_at            timestamptz not null
```

枚举：

```text
source_type:
  upload | semantic_scholar | deep_search | manual | bibtex

library_status:
  candidate | included | core | excluded | used_in_draft

evidence_level:
  metadata_only | external_verified | uploaded_fulltext | indexed_fulltext

fulltext_status:
  none | uploaded | preprocessing | indexed | failed

read_status:
  unread | reading | read | skimmed
```

约束：

```text
unique(workspace_id, citation_key)
unique(workspace_id, doi) where doi is not null and is_deleted = false
index(workspace_id, library_status)
index(workspace_id, source_type)
index(workspace_id, evidence_level)
index(workspace_id, fulltext_status)
index(workspace_id, normalized_title)
```

设计说明：

1. `workspace_id + citation_key` 唯一，因为 citation key 是 workspace 内 LaTeX 引用身份。
2. `doi` 在 workspace 内唯一，不做全局唯一，避免跨 workspace 状态和权限污染。
3. `library_status=candidate` 是 deep search 默认状态。
4. `evidence_level` 表达证据强度，不与 `library_status` 混淆。

### 5.2 `reference_external_ids`

外部 ID 独立表，避免 JSONB 唯一约束复杂化。

字段：

```text
id             uuid pk
workspace_id   varchar(36) not null index
reference_id   uuid not null fk workspace_references(id) on delete cascade
source         varchar(40) not null
external_id    text not null
url            text null
created_at     timestamptz not null
```

约束：

```text
unique(workspace_id, source, external_id)
index(reference_id)
```

示例：

```text
source = semantic_scholar
external_id = Semantic Scholar paperId
```

### 5.3 `reference_assets`

全文和衍生文件资产表。

字段：

```text
id                    uuid pk
workspace_id           varchar(36) not null index
reference_id           uuid not null fk workspace_references(id) on delete cascade

asset_type             varchar(40) not null
file_path              text not null
virtual_path           text null
public_url             text null
content_type           varchar(120) null
file_size              bigint null
file_hash              varchar(128) null

page_count             int null
language               varchar(20) null

preprocess_status      varchar(30) not null default 'pending'
preprocess_task_id     varchar(36) null
preprocess_error       text null
manifest_path          text null
markdown_paths         jsonb not null default []

created_at             timestamptz not null
updated_at             timestamptz not null
```

枚举：

```text
asset_type:
  pdf | markdown | manifest | image | supplementary

preprocess_status:
  pending | running | succeeded | failed | skipped
```

设计说明：

1. 上传 PDF 不写旧 `papers.file_path`。
2. 一个 reference 可有多个 asset，例如原始 PDF、markdown、manifest、图片。
3. asset 与 workspace 强绑定，避免跨 workspace 文件泄漏。

### 5.4 `reference_outline_nodes`

目录树。模型 page index 的第一层输入。

字段：

```text
id                    uuid pk
workspace_id           varchar(36) not null index
reference_id           uuid not null fk workspace_references(id) on delete cascade
parent_id              uuid null fk reference_outline_nodes(id) on delete cascade

section_path           varchar(80) not null
title                  text not null
normalized_title        text not null
level                  int not null
sort_order             int not null

page_start             int null
page_end               int null
char_start             int null
char_end               int null

summary                text null
keywords               jsonb not null default []

created_at             timestamptz not null
updated_at             timestamptz not null
```

约束：

```text
unique(reference_id, section_path)
index(workspace_id, reference_id)
index(workspace_id, normalized_title)
```

设计说明：

1. `section_path` 可为 `1`、`2.3`、`Appendix A` 等。
2. `summary` 可由解析或后处理生成，帮助模型快速判断是否读取正文。
3. 模型先看本表，不直接看全文。

### 5.5 `reference_text_units`

正文读取单位。模型决定召回后，系统读取这里。

字段：

```text
id                    uuid pk
workspace_id           varchar(36) not null index
reference_id           uuid not null fk workspace_references(id) on delete cascade
outline_node_id        uuid null fk reference_outline_nodes(id) on delete set null
asset_id               uuid null fk reference_assets(id) on delete set null

unit_type              varchar(30) not null
unit_index             int not null
page_start             int null
page_end               int null

content                text not null
token_count            int null
char_start             int null
char_end               int null

search_text            text not null
metadata               jsonb not null default {}

created_at             timestamptz not null
updated_at             timestamptz not null
```

枚举：

```text
unit_type:
  section | page | paragraph | chunk | abstract
```

索引：

```text
index(workspace_id, reference_id)
index(workspace_id, outline_node_id)
GIN(to_tsvector('simple', search_text))
```

设计说明：

1. 第一版不用向量库。
2. `search_text` 用 PostgreSQL FTS / `ts_rank`。
3. 没有全文的 metadata-only 文献，可以生成一条 `unit_type=abstract` 的 text unit。

### 5.6 `reference_usage_events`

记录写作中哪些证据被使用，为 citation 校验和未来数据产品服务。

字段：

```text
id                         uuid pk
workspace_id                varchar(36) not null index
reference_id                uuid not null fk workspace_references(id)
outline_node_id             uuid null fk reference_outline_nodes(id)
text_unit_id                uuid null fk reference_text_units(id)

execution_session_id        varchar(36) null
task_id                     varchar(36) null
artifact_id                 varchar(36) null
latex_project_id            varchar(36) null

target_section              varchar(120) null
claim_text                  text null
generated_text              text null
citation_key                varchar(120) not null
usage_type                  varchar(40) not null
accepted_status             varchar(30) not null default 'pending'

created_at                  timestamptz not null
```

枚举：

```text
usage_type:
  background | comparison | method_support | dataset | limitation | result_discussion | citation_only

accepted_status:
  pending | accepted | edited | rejected
```

设计说明：

1. 短期用于引用追踪和 UI 展示“被哪些章节引用”。
2. 长期用于训练科研 workflow 数据产品：query、选文献、读章节、生成段落、用户采纳之间的链路。

### 5.7 `reference_bibtex_snapshots`

`refs.bib` projection 快照。不是事实源。

字段：

```text
id                    uuid pk
workspace_id           varchar(36) not null index
latex_project_id       varchar(36) null
scope                  varchar(40) not null
content                text not null
reference_count        int not null
checksum               varchar(128) not null
created_at             timestamptz not null
```

枚举：

```text
scope:
  used_only | core | included_and_core | all_non_excluded
```

设计说明：

1. `refs.bib` 由 `workspace_references` 生成。
2. snapshot 只用于审计、回滚和 Prism 同步记录。

## 6. 服务架构

### 6.1 `WorkspaceReferenceService`

唯一主 CRUD 和状态管理服务。

职责：

```text
list_references
get_reference
create_reference
update_reference
soft_delete_reference
mark_candidate
mark_included
mark_core
mark_excluded
mark_used_in_draft
find_duplicate
generate_or_reserve_citation_key
```

禁止：

```text
任何 feature service 直接写 workspace_references
任何 import/preprocess service 绕过 citation_key 生成
```

### 6.2 `ReferenceImportService`

所有来源导入统一入口。

方法：

```text
import_uploaded_pdf
import_semantic_scholar_papers
import_deep_search_artifact
import_bibtex
import_manual
```

统一返回：

```json
{
  "created": 0,
  "updated": 0,
  "skipped": 0,
  "references": []
}
```

导入状态规则：

```text
Semantic Scholar:
  source_type = semantic_scholar
  library_status = candidate
  evidence_level = external_verified
  fulltext_status = none

Deep search:
  source_type = deep_search
  source_run_id / source_artifact_id
  library_status = candidate
  evidence_level = external_verified
  fulltext_status = none

Upload PDF:
  source_type = upload
  library_status = included
  evidence_level = uploaded_fulltext
  fulltext_status = uploaded / preprocessing

Manual:
  source_type = manual
  library_status = included
  evidence_level = metadata_only
  fulltext_status = none

BibTeX:
  source_type = bibtex
  library_status = included
  evidence_level = metadata_only
  fulltext_status = none
```

去重规则：

```text
same workspace + same external id -> update existing
same workspace + same DOI -> update existing
same workspace + normalized title + year -> candidate merge with low confidence flag
different workspace -> independent reference
```

### 6.3 `ReferencePreprocessService`

处理 PDF 到 manifest、outline、text units。

流程：

```text
reference upload
  -> create workspace_reference
  -> create reference_asset
  -> submit reference_preprocess task
  -> layout parsing / OCR / markdown
  -> metadata enrichment
  -> outline_nodes write
  -> text_units write
  -> reference.fulltext_status = indexed
  -> reference.evidence_level = indexed_fulltext
```

新任务类型：

```text
reference_preprocess
```

替代旧：

```text
document_preprocess 作为文献预处理主链路
paper_extraction 作为文献中心主链路
```

### 6.4 `ReferenceIndexService`

目录和正文读取。

方法：

```text
get_library_outline
get_reference_outline
read_outline_node
read_pages
search_text_units
```

关键设计：

```text
get_library_outline:
  给模型看所有文献摘要 + citation_key + outline，不含全文。

read_outline_node:
  模型选择后读取指定章节。

search_text_units:
  作为辅助检索，不是主 RAG。
```

### 6.5 `ReferenceEvidenceService`

写作取证服务。实现 outline-first evidence retrieval。

方法：

```text
build_reference_catalog_brief
plan_evidence_reading
build_evidence_pack
```

内部流程：

```text
1. 加载 workspace reference catalog + outlines
2. 让模型决定读取哪些 reference / outline node / pages
3. 系统读取 text_units
4. 返回 evidence pack
```

输入：

```json
{
  "workspace_id": "...",
  "target_section": "related_work",
  "writing_goal": "compare tool-using LLM agents",
  "claim_plan": ["...", "..."],
  "max_references": 8,
  "max_text_units": 20
}
```

输出：

```json
{
  "selected_references": [
    {
      "reference_id": "...",
      "citation_key": "Yao2023",
      "outline_node_ids": ["..."],
      "reason": "supports method comparison"
    }
  ],
  "evidence_units": [
    {
      "reference_id": "...",
      "citation_key": "Yao2023",
      "outline_node_id": "...",
      "section_title": "Method",
      "pages": "4-6",
      "content": "..."
    }
  ],
  "missing_evidence": []
}
```

### 6.6 `ReferenceBibTeXService`

唯一 BibTeX 和 citation validation 服务。

职责：

```text
build_citation_key_base
ensure_unique_citation_key
build_bibtex_entry
build_refs_bib
validate_citations
sync_refs_to_prism
```

citation key 规则：

```text
FirstAuthorYear
FirstAuthorYearShortTitle
碰撞时追加 a/b/c
```

示例：

```text
Yao2023
Yao2023ReAct
Smith2024a
Smith2024b
```

约束：

```text
citation_key 入库后默认稳定
修改 citation_key 必须校验已存在正文引用
LLM 不允许创建 citation_key
BibTeX 不允许由 LLM 自由生成
```

### 6.7 `ReferenceUsageService`

记录 evidence 到正文的使用关系。

方法：

```text
record_usage
list_usage_by_reference
list_usage_by_artifact
mark_usage_accepted
mark_usage_rejected
```

## 7. API 设计

统一新路由：

```text
/workspaces/{workspace_id}/references
```

### 7.1 Catalog API

```http
GET /workspaces/{workspace_id}/references
GET /workspaces/{workspace_id}/references/{reference_id}
PATCH /workspaces/{workspace_id}/references/{reference_id}
DELETE /workspaces/{workspace_id}/references/{reference_id}
```

列表过滤：

```text
status
source_type
evidence_level
fulltext_status
read_status
query
limit
offset
```

状态操作：

```http
POST /workspaces/{workspace_id}/references/{reference_id}/mark-included
POST /workspaces/{workspace_id}/references/{reference_id}/mark-core
POST /workspaces/{workspace_id}/references/{reference_id}/exclude
POST /workspaces/{workspace_id}/references/{reference_id}/mark-read
```

### 7.2 Import API

```http
POST /workspaces/{workspace_id}/references/upload
POST /workspaces/{workspace_id}/references/import/semantic-scholar
POST /workspaces/{workspace_id}/references/import/deep-search-artifact
POST /workspaces/{workspace_id}/references/import/bibtex
POST /workspaces/{workspace_id}/references/manual
```

上传 PDF 不再走旧 `/papers/upload`。

### 7.3 Index API

```http
GET /workspaces/{workspace_id}/references/outline
GET /workspaces/{workspace_id}/references/{reference_id}/outline
GET /workspaces/{workspace_id}/references/{reference_id}/outline/{node_id}/content
GET /workspaces/{workspace_id}/references/{reference_id}/pages?page_start=1&page_end=3
POST /workspaces/{workspace_id}/references/search-text-units
```

### 7.4 Evidence API

```http
POST /workspaces/{workspace_id}/references/evidence-pack
```

第一版可只供后端 feature service 调用，不必马上暴露给前端。

### 7.5 BibTeX API

```http
GET /workspaces/{workspace_id}/references/bibtex?scope=used_only
POST /workspaces/{workspace_id}/references/bibtex/validate
POST /workspaces/{workspace_id}/references/bibtex/sync-prism
```

validate 输入：

```json
{
  "latex_content": "... \\cite{Yao2023}"
}
```

validate 输出：

```json
{
  "valid": true,
  "missing_keys": [],
  "unused_bib_keys": [],
  "unverified_keys": []
}
```

## 8. 前端设计

重做 `LiteraturePanel` 为 `ReferenceLibraryPanel`。中文仍叫“文献中心”。

### 8.1 顶部统计

```text
全部
候选
已纳入
核心
已引用
已索引全文
解析中
```

### 8.2 筛选

```text
来源 source_type
文献状态 library_status
证据等级 evidence_level
全文状态 fulltext_status
年份
关键词搜索
```

### 8.3 文献卡片字段

```text
title
authors / year / venue
citation_key
source_type badge
library_status badge
evidence_level badge
fulltext_status badge
doi / Semantic Scholar id
used count
```

### 8.4 操作

```text
标为核心
纳入参考池
排除
上传全文
重新解析
查看目录
查看 BibTeX
复制 \cite{key}
查看使用位置
```

### 8.5 详情 Drawer

```text
Metadata
Outline
Indexed sections/pages
BibTeX
Usage events
Source history
Preprocess status
```

## 9. Agent 工具设计

删除或替换旧工具：

```text
list_workspace_literature_toc
search_workspace_literature
read_workspace_literature_section
```

新增工具：

```text
list_reference_library
list_reference_outlines
read_reference_outline_node
search_reference_text_units
build_reference_evidence_pack
validate_reference_citations
```

工具优先级：

```text
写作 Agent 优先：
  list_reference_library
  list_reference_outlines
  read_reference_outline_node

不确定目录时辅助：
  search_reference_text_units

写作 feature service 推荐：
  build_reference_evidence_pack
```

## 10. 功能链路

### 10.1 上传 PDF

```text
POST /references/upload
  -> ReferenceImportService.import_uploaded_pdf
  -> create workspace_reference
  -> create reference_asset
  -> submit reference_preprocess task
  -> extract metadata / markdown / outline / text units
  -> update fulltext_status / evidence_level
  -> SSE update ReferenceLibraryPanel
```

### 10.2 Semantic Scholar 检索

```text
literature_search feature
  -> LiteratureSearchService.search
  -> ReferenceImportService.import_semantic_scholar_papers
  -> workspace_references candidate
  -> task_result shows discovered / created / updated
  -> next_steps open reference library
```

### 10.3 Deep Research

```text
deep_research feature
  -> produces verified paper set
  -> ReferenceImportService.import_deep_search_artifact
  -> candidates in reference library
  -> artifact remains research report
```

### 10.4 写作

```text
writing feature
  -> ReferenceEvidenceService.build_evidence_pack
  -> LLM writes only with allowed citation_key
  -> ReferenceBibTeXService.validate_citations
  -> ReferenceUsageService.record_usage
  -> Prism pending main.tex
  -> Prism pending refs.bib
```

### 10.5 编译

```text
compile feature
  -> extract \cite{} from main.tex
  -> validate against workspace_references
  -> generate refs.bib if stale/missing
  -> compile
  -> report missing/unverified citations
```

## 11. Prism 衔接

写作任务如果使用 citation，必须产生两个 pending file changes：

```text
main.tex
refs.bib
```

禁止：

```text
正文有 \cite{} 但 refs.bib 没更新
refs.bib 有模型编造条目
citation key 不存在文献中心
```

`ReferenceBibTeXService.sync_refs_to_prism` 应负责：

```text
build_refs_bib(scope)
create/update refs.bib pending change
return prism sync summary
```

`task_result` 应显示：

```text
used_citations_count
refs_bib_entries_count
missing_citations
unverified_citations
prism_pending_file_changes
```

## 12. 旧代码清理范围

### 12.1 后端模型/服务

删除或替换：

```text
backend/src/database/models/paper.py
backend/src/database/models/workspace_literature.py
backend/src/database/models/citation.py
backend/src/services/literature_service.py
backend/src/academic/literature/index_service.py 的 Paper-based 实现
backend/src/academic/citation/*
backend/src/tools/builtins/literature.py 旧工具
```

如果某些目录暂时仍被 import，需要在同一阶段替换调用点，不保留业务入口。

### 12.2 后端 API

删除或替换：

```text
backend/src/gateway/routers/literature.py
backend/src/gateway/routers/papers.py 中作为文献中心的入口
/workspaces/{workspace_id}/papers
/papers/upload
/workspaces/{workspace_id}/literature
/workspaces/{workspace_id}/literature/import
```

新入口统一为：

```text
backend/src/gateway/routers/references.py
```

### 12.3 Feature services

替换：

```text
sci_feature_service._load_workspace_literature
thesis_feature_service._load_workspace_literature
thesis_feature_service._build_bibtex
所有直接调用 LiteratureService 的 feature service
```

新调用：

```text
ReferenceEvidenceService
ReferenceBibTeXService
WorkspaceReferenceService
```

### 12.4 前端

替换：

```text
frontend/app/(workbench)/workspaces/[id]/components/LiteraturePanel.tsx
frontend/stores/workspace.ts 中 papers 作为文献中心状态
frontend/lib/api/workspace.ts 中旧 literature/paper API
ImportLiteratureButton 旧 source/artifact import 语义
```

新增：

```text
ReferenceLibraryPanel
reference store
references API client
reference status badges
outline drawer
bibtex drawer
```

## 13. 测试与门禁

### 13.1 架构约束测试

必须新增测试，防止旧体系复活：

```text
feature services 不允许 import LiteratureService
frontend 文献中心不允许 fetchPapers
new reference API 不允许调用 old paper/literature routers
BibTeX 不允许由 thesis_feature_service 私有函数生成
```

### 13.2 Schema / service 测试

覆盖：

```text
create reference
generate citation_key
same DOI same workspace dedupe
same Semantic Scholar id same workspace dedupe
same DOI different workspace allowed
mark core/included/excluded
soft delete
```

### 13.3 Import 测试

覆盖：

```text
upload PDF creates reference + asset + preprocess task
semantic scholar import creates candidate references
deep search artifact import creates candidate references
bibtex import creates included references
manual creates included reference
```

### 13.4 Page index 测试

覆盖：

```text
reference_preprocess writes outline_nodes
reference_preprocess writes text_units
list_reference_outlines returns tree
read_reference_outline_node returns content
search_reference_text_units returns ranked FTS results
```

### 13.5 Evidence / writing 测试

覆盖：

```text
build_evidence_pack returns selected references and text units
writing output with unknown \cite{} fails validation
writing output with allowed citation records usage event
metadata_only reference is marked lower evidence strength
```

### 13.6 BibTeX / Prism 测试

覆盖：

```text
citation key collisions get suffix
refs.bib uses stored citation_key
refs.bib scope used_only/core/included works
main.tex citation validation catches missing keys
writing with citations creates main.tex + refs.bib pending changes
```

## 14. 执行阶段

### Phase A：Schema Cutover

目标：建新表，清旧表/旧模型业务入口。

任务：

1. 新增 `workspace_references`、`reference_external_ids`、`reference_assets`、`reference_outline_nodes`、`reference_text_units`、`reference_usage_events`、`reference_bibtex_snapshots`。
2. 删除旧 `WorkspaceLiterature` 主链路。
3. 删除旧 `Paper/WorkspacePaper` 作为文献中心主链路。
4. 新增 ORM models。
5. 新增 schema/service 单元测试。

验收：

```text
所有新表可创建
WorkspaceReferenceService 基础 CRUD 通过
citation_key 唯一约束通过
旧 LiteratureService 不再被新代码引用
```

### Phase B：Reference API + Frontend Catalog

目标：文献中心 UI 只读新 references API。

任务：

1. 新增 `backend/src/gateway/routers/references.py`。
2. 新增 frontend references API client。
3. 重写 `LiteraturePanel` 为 `ReferenceLibraryPanel`。
4. 增加状态 badges 和筛选。
5. 支持复制 `\cite{key}`。

验收：

```text
手动创建/导入/上传的 reference 都出现在同一列表
前端不再依赖 papers store 作为文献中心
```

### Phase C：Import + Preprocess

目标：所有来源进入 references，PDF 可进入 page index。

任务：

1. 实现 `ReferenceImportService`。
2. 新增 `/references/upload`。
3. 新增 `reference_preprocess` task。
4. 写入 `reference_assets`。
5. 写入 `reference_outline_nodes` 和 `reference_text_units`。
6. SSE 更新文献中心状态。

验收：

```text
上传 PDF -> preprocessing -> indexed
Semantic Scholar -> candidate references
deep search -> candidate references
无双写旧表
```

### Phase D：Outline-first Evidence

目标：写作可通过文献中心 page index 取证。

任务：

1. 实现 `ReferenceIndexService`。
2. 实现 `ReferenceEvidenceService`。
3. 新增 agent tools。
4. SCI/thesis 写作服务改用 evidence pack。
5. 输出引用必须受 evidence pack 限制。

验收：

```text
模型可先看目录，再读取指定章节
写作输出未知 citation_key 会失败或进入 task_failure
```

### Phase E：BibTeX + Prism

目标：正文引用和 `refs.bib` 同步进入 Prism。

任务：

1. 实现 `ReferenceBibTeXService`。
2. 实现 citation validation。
3. 写作任务生成 `main.tex` pending change 时同步 `refs.bib`。
4. compile 前执行 citation validation。
5. task_result 显示引用状态。

验收：

```text
main.tex 中所有 \cite{} 都存在于 refs.bib
refs.bib 全部来自 workspace_references
Prism pending changes 同时包含正文和 refs.bib
```

### Phase F：Usage Tracking

目标：记录证据使用链路。

任务：

1. 实现 `ReferenceUsageService`。
2. 写作后记录 `reference_usage_events`。
3. 文献详情展示被哪些章节/任务使用。
4. apply/reject 后更新 usage accepted_status。

验收：

```text
每个正文引用可追溯到 reference / outline node / text unit
文献中心能显示 used_in_draft
```

## 15. 推荐并行分工

如果多 agent 并行：

1. Agent A：Schema + ORM + `WorkspaceReferenceService`，独占数据库模型。
2. Agent B：Reference API + frontend `ReferenceLibraryPanel`，不改 preprocess。
3. Agent C：Import + upload + `reference_preprocess` task，独占上传/任务链路。
4. Agent D：Index + evidence tools，独占 agent tools 和 writing service 取证。
5. Agent E：BibTeX + Prism + compile validation，独占 Prism/LaTeX 引用链路。

并行约束：

1. 不允许两个 agent 同时修改 schema models。
2. 不允许旧 `LiteratureService` 被任何新代码重新引用。
3. 所有入口必须通过 `WorkspaceReferenceService` 或其上层服务。
4. 前端只读 `/references` API，不再读 `/papers` 或旧 `/literature` 作为文献中心。

## 16. 完成定义

完成后系统应达到：

```text
用户上传 PDF、deep search 发现、Semantic Scholar 检索、手动添加、BibTeX 导入
  -> 全部进入同一个文献中心。

模型写作前
  -> 先看文献中心目录
  -> 决定读取哪些文献章节/page
  -> 系统返回 evidence pack。

模型写作时
  -> 只能使用 evidence pack 中的 citation_key。

写入 Prism 时
  -> main.tex 和 refs.bib 同步进入 pending review。

编译前
  -> 所有 \cite{} 都能在 workspace_references / refs.bib 中找到。

文献中心
  -> 能展示候选、核心、已引用、已索引、解析失败等状态。
```

一句话定义：

```text
Workspace Reference Library 成为问津从调研到终稿的唯一证据底座。
```
