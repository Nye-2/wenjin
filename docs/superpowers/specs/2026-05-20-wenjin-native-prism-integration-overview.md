# Wenjin-native Prism Integration Overview

Date: 2026-05-20
Status: Implemented Product Architecture / Current Context

## 1. Overview

Workspace Prism surface 已经完成产品级收敛：

- workspace 与 Prism 有显式 `LatexProject.workspace_id / surface_role` 绑定
- workspace-owned manuscript 的 canonical route 是 `/workspaces/:id/prism`
- historical workspace-owned `/latex/:projectId` UI / page route 已被移除；不再通过 redirect 兼容旧入口
- Compute projection 优先读取 workspace 绑定的 authoritative Prism state
- result card / completed view / Prism Changes tab 共享 DB-backed review item projection
- Prism action 会落到 `/workspaces/:id/prism?focus=file_changes&review_item_id=...&logical_key=...`
- 数据库通过 partial unique index 保证一个 workspace 只有一个 primary manuscript
- `prism_review_items` / `prism_source_links` / `prism_protected_sections` 承载 review、provenance、manual-protect 事实
- launch context 向 Lead Agent 注入 lightweight manuscript context，而不是完整正文

这意味着链路已经从“workspace 挂了一个 manuscript editor”收敛为：

**Prism 不只是 Wenjin 里的稿件编辑器，而应该成为 Wenjin workspace 的 manuscript collaboration surface。**

它要和 Wenjin 的三条核心能力原生联动：

1. **Research context**：Library / Documents / Decisions / Memory 给稿件提供来源、材料、偏好与决策依据。
2. **Agent execution**：Chat Agent / Lead Agent / TaskReport 给稿件提供结构化写作变更、解释、引用与审阅建议。
3. **Result review loop**：result_card / Compute / rooms / Prism file changes 共享同一个“预览、接受、回写、追踪”的结果契约。

目标不是把 Prism 塞进更多入口，而是让用户在同一个 workspace 中自然完成：

```text
研究材料进入 workspace
  -> agent 生成结构化写作建议
  -> Prism 呈现可审阅稿件变更
  -> 用户接受 / 拒绝 / 手改
  -> 变更、来源、决策和偏好回写 workspace
  -> 下一轮 agent 写作理解最新稿件状态
```

本 overview 采用一次性收敛原则：后续实现不新增 workspace-owned Prism 的兼容层、runtime fallback、双写、双读或 frontend-only 事实源。历史数据通过 migration 进入 canonical schema；运行时只走新链路。

Implementation closure on 2026-05-20:

1. Canonical schema landed in `backend/alembic/versions/058_prism_canonical_review_tables.py`.
2. Workspace projection, Compute projection, result cards, completed view, and Prism Changes tab now use the same DB-backed review state.
3. Source links are generated from canonical Prism review content and workspace references, then deep-link back to Library / Documents.
4. Prism apply / reject / defer / revert and manual protection write workspace activity and refresh the Prism context rail.
5. Execution launch injects lightweight `manuscript_context` into `TaskBrief`; protected sections and pending review items are visible to later agent work.
6. Full local gate passed: backend tests, frontend typecheck/lint/unit/build, and full Playwright E2E.

## 2. Product Positioning

### 2.1 Current Product Identity

当前 Wenjin 的 workspace 由两类主 surface 组成：

| Surface | Route | Product Role |
| --- | --- | --- |
| Workbench | `/workspaces/:id` | 对话、能力启动、执行观察、rooms 消费 |
| Prism | `/workspaces/:id/prism` | 主稿编辑、编译、文件变更审阅 |

这个结构是当前产品结构，后续扩展不改变它。

### 2.2 Target Product Identity

目标身份：

> Prism 是 workspace 的主稿协作面，负责把 research context、agent output、manual edit 与 final manuscript 统一在一个可审阅、可追溯、可回写的稿件工作流中。

它不是：

- 一个孤立的 LaTeX 项目列表
- 一个 Compute 右侧小挂件
- 一个 room drawer
- 一个只负责文件读写的 editor shell

它应该是：

- workspace 的第二主工作面
- manuscript state 的产品入口
- agent 写作变更的审阅入口
- evidence / citation / decision 与正文绑定的界面
- 用户写作偏好和稿件事实回流到 workspace memory 的触点

### 2.3 Workspace Room Coverage

Wenjin workspace 有 8 个 rooms。Prism integration 必须显式声明联动边界，避免“整体打通”变成无边界扩张。

| Room | Prism Integration Level | First-Phase Role |
| --- | --- | --- |
| Library | Deep | source links、citation usage、reference detail deep-link |
| Documents | Deep | source links、material excerpts、document detail deep-link |
| Decisions | Deep | writing decisions、terminology、structure rules |
| Memory | Deep | reviewed writing preferences、style constraints |
| Run History | Deep | execution / task provenance、apply/reject activity |
| Tasks | Boundary | 只暴露与稿件相关的 task provenance；不把 task management 放进 Prism |
| Sandbox | Boundary | 编译 / artifact references only；不把 sandbox console 放进 Prism |
| Settings | Boundary | 只读取 workspace policy / preferences；不在 Prism 内做 settings 管理 |

首阶段深联动范围是 Library / Documents / Decisions / Memory / Run History。Tasks / Sandbox / Settings 只保留边界引用，不进入 Prism context rail 的核心交互。

## 3. Integration Principles

### P1. Workspace remains the product container

Prism 不拥有独立产品身份。所有 workspace-owned Prism 行为都必须带着 `workspace_id`，并服从 workspace owner、workspace type、capability、rooms、execution 的边界。

### P2. Prism owns manuscript editing, not research storage

Prism 管主稿文件、编译、PDF、pending changes、apply/revert。Library / Documents / Decisions / Memory 仍然是各自 room 的事实源。Prism 只引用、消费、展示、回写摘要，不复制 room 数据。

### P3. Agent writes proposals, user owns manuscript state

Lead Agent 不能直接覆盖用户稿件。Agent output 进入 Prism pending changes；用户在 Prism 或 result review surface 中接受后，才写入文件。

### P4. Every manuscript change needs provenance

用户应该能知道一段 proposed change 来自哪个 execution、哪个 task、哪些 sources、哪条 decision、哪个 memory preference。没有 provenance 的 agent 写作只能作为低信任文本。

### P5. Review contracts must converge

`result_card` checkbox、Compute completed view、Prism file-change review 已收敛成统一的 review item contract：

```text
review item
  -> preview
  -> accept / reject / defer
  -> apply target
  -> audit / activity
```

### P6. Manual edits are first-class signals

用户在 Prism 里手动修改、拒绝建议、保护段落，都是重要反馈。系统要能把这些行为变成 activity、decision candidate 或 memory candidate，而不是只留在文件系统里。

Manual edit feedback 必须遵守 curated review：系统可以生成 candidate，不能自动写入 Decisions / Memory。

### P7. Clean migration over compatibility

当前实现必须继续走 canonical schema 和单一路径：

- `ResultReviewItem` 是 backend contract / DB-backed review state，不是 frontend-only projection。
- provenance links 进入 dedicated tables，不继续膨胀 `LatexProject.llm_config.metadata`。
- protected sections 进入 dedicated contract，不靠 editor-local state。
- runtime 不做“先查新表，失败再扫旧 payload / metadata”的 fallback。
- standalone LaTeX UI / page route 不再作为 workspace-owned manuscript 入口；workspace-owned manuscript 只认 workspace Prism surface。

历史数据迁移是一次性 migration 工作；迁移后运行时代码只消费新结构。

### P8. Context stays lightweight

Agent-aware manuscript context 只能传 lightweight projection：

- outline
- target file list
- section map
- protected sections
- pending review summary
- source/provenance ids
- content hashes
- necessary short excerpts

完整正文、完整 diff、PDF、全文材料不直接塞进 `TaskBrief`。需要全文时，由 subagent 通过明确工具按需读取。

## 4. Core Product Loops

### Loop A: Context-to-Manuscript

用户把材料放进 workspace，agent 写进稿件。

```text
Library / Documents
  -> capability brief / lead runtime context
  -> TaskReport writing outputs
  -> Prism pending file changes
  -> user review
  -> manuscript files
```

关键要求：

- 写作任务能声明使用了哪些 room items。
- Prism pending change 能展示来源摘要和 citation candidate。
- 接受后，manuscript file 与 source usage 建立可追踪关系。

### Loop B: Manuscript-to-Workspace

用户在 Prism 修改稿件，workspace 理解这些变化。

```text
Prism manual edit / apply / reject
  -> Workspace Activity
  -> Run History / Execution linkage
  -> Decision / Memory candidate
  -> future agent context
```

关键要求：

- apply / discard / revert 进入 workspace activity。
- 用户保护段落、反复拒绝某类建议，应生成 Memory candidate，并等待用户确认。
- 用户确定题目、章节结构、术语翻译、写作规则，应生成 Decision candidate，并等待用户确认。

### Loop C: Result Review Convergence

执行结果、room 写入、Prism 改稿走同一条用户确认模型。

```text
TaskReport outputs
  -> ResultReviewItem[]
  -> CompletedView / ResultCard / Prism review panel
  -> accept selected
  -> room commit or prism apply
```

关键要求：

- result review item 支持不同 target：`room_item`、`prism_file_change`、`memory_candidate`、`decision_candidate`。
- UI 文案和状态统一，不再一处叫“全部接受”、另一处叫“apply file changes”。
- commit/apply 后产生统一 activity。

### Loop D: Agent-Aware Manuscript State

下一轮 agent 写作能看到当前稿件状态，而不是只看到旧 execution payload。

```text
WorkspacePrismService surface projection
  -> manuscript outline / file map / protected sections / pending changes
  -> feature launch context
  -> Lead Agent TaskBrief
```

关键要求：

- `launch_feature` context 中加入 lightweight manuscript projection。
- pending changes 未处理时，agent 要知道“现有建议未确认”，避免叠加写入冲突。
- protected sections 不被 agent 直接改写，只能生成 review suggestion。
- launch context 不传完整稿件正文；全文读取必须是后续 subagent 的显式动作。

## 5. User Experience Model

### 5.1 Workspace Surface Switch

Surface switch 保持两个主 tab：

- Workbench：讨论、计划、执行、材料、结果消费
- Prism：稿件、编译、文件变更审阅、引用检查

新增的不是第三个 surface，而是两个 surface 之间的深联动。

### 5.2 Prism Context Rail

Prism 需要一个 workspace-aware context rail 或 side panel，用于显示和操作与当前稿件相关的 workspace 信息。

首版建议分四个 tabs：

| Tab | Purpose |
| --- | --- |
| Sources | 当前文件/段落关联的 Library / Documents 来源 |
| Changes | Agent proposed changes、manual conflict、apply/reject |
| Decisions | 与当前稿件相关的写作决策、术语、结构约定 |
| Activity | 最近 apply/reject/compile/execution 事件 |

这个 rail 不取代 rooms，它只是把 rooms 中与稿件当前位置相关的部分带到 Prism。

### 5.3 Result Review Entry

用户从 Workbench 完成写作任务后：

1. CompletedView 显示结果摘要和 Prism changes。
2. “预览待确认修改”进入 `/workspaces/:id/prism?focus=file_changes&review_item_id=...&logical_key=...`。
3. Prism Changes tab 展示每个 review item：
   - target file
   - diff preview
   - source execution / task
   - used references / documents
   - accept / reject / protect target section
4. 用户确认后，activity 与 provenance 写回 workspace。

### 5.4 Manual Edit Feedback

用户在 Prism 手动编辑后：

- 默认只保存文件，不打扰用户。
- 当编辑触及 agent-managed section 或 pending change target 时，Prism 提示可选动作：
  - mark section protected
  - save as writing preference
  - record as decision
  - ignore

这样反馈是轻量的，不把 editor 变成表单。

## 6. Domain Contracts

### 6.1 Workspace Prism Surface Projection

现有 projection 已包含：

```text
workspace_id
latex_project_id
surface_role
url
main_file
compile_status
has_pending_changes
target_files
file_changes
applied_file_changes
```

当前实现已经建立 canonical persistent contracts，并以 product projection 对外暴露。新增产品语义不继续写进 `LatexProject.llm_config.metadata`：

```text
prism_review_items
- id
- workspace_id
- latex_project_id
- source_type
- source_execution_id
- source_task_id
- target_kind
- target_file_path
- target_room
- target_item_id
- status
- preview_payload
- created_at / updated_at / applied_at

prism_source_links
- id
- workspace_id
- latex_project_id
- review_item_id
- source_type
- source_id
- file_path
- section_key
- citation_key
- usage

prism_protected_sections
- id
- workspace_id
- latex_project_id
- file_path
- section_key
- scope
- reason
- source
```

这些表是 Prism 与 Wenjin 深度适配的事实源。迁移后 runtime 不再从旧 payload / metadata 中推断同一语义。

product projection 从上述 canonical tables 聚合：

```ts
type WorkspacePrismSurfaceProjection = {
  workspace_id: string;
  latex_project_id: string;
  surface_role: "primary_manuscript";
  url: string;
  manuscript: {
    main_file: string;
    target_files: string[];
    outline: ManuscriptOutlineNode[];
    protected_sections: ProtectedSection[];
  };
  review: {
    pending_items: ResultReviewItem[];
    applied_items: ResultReviewItem[];
    unresolved_conflicts: PrismConflict[];
  };
  context: {
    source_links: PrismSourceLink[];
    decisions: PrismDecisionLink[];
    memory_preferences: PrismMemoryLink[];
    recent_activity: PrismActivityItem[];
  };
  compile: {
    status: "idle" | "success" | "failed" | "running";
    pdf_endpoint?: string | null;
    last_error?: string | null;
  };
};
```

注意：这个 projection 是读取模型，不是新的持久层。

### 6.2 ResultReviewItem

统一 review contract：

```ts
type ResultReviewItem = {
  id: string;
  source: "execution" | "manual_edit" | "room_import";
  source_execution_id?: string | null;
  source_task_id?: string | null;
  target: {
    kind: "prism_file_change" | "room_item" | "memory_candidate" | "decision_candidate";
    workspace_id: string;
    file_path?: string | null;
    room?: "library" | "documents" | "decisions" | "memory" | null;
    item_id?: string | null;
  };
  title: string;
  summary: string | null;
  status: "pending" | "accepted" | "applied" | "rejected" | "deferred" | "reverted";
  preview: {
    mode: "diff" | "markdown" | "plain_text" | "citation" | "json";
    before?: string | null;
    after?: string | null;
    body?: string | null;
  };
  provenance: {
    sources: PrismSourceLink[];
    decisions: PrismDecisionLink[];
    memory: PrismMemoryLink[];
  };
};
```

Review state 由 backend 持久化，frontend 只维护临时勾选 UI。状态机：

```text
pending
  -> accepted
  -> applied
  -> reverted

pending
  -> rejected

pending
  -> deferred
  -> accepted / rejected
```

语义：

- `pending`：系统生成 review item，等待用户决定。
- `accepted`：用户确认接受，目标写入尚未完成或正在事务中处理。
- `applied`：目标已经写入 Prism 文件或 room，并完成 audit/activity。
- `rejected`：用户拒绝，目标不变。
- `deferred`：用户暂缓，目标不变，但保留 item。
- `reverted`：曾经 applied 的变更被用户回滚。

`selected` 不是持久状态，只是前端批量操作前的临时 UI state。

Prism file changes 必须一次性迁移到这个 contract；后续不再维护并行 file-change review state。

### 6.3 Provenance Links

稿件 provenance 不塞进正文注释或 `LatexProject.llm_config.metadata` 里作为事实源。当前直接使用 `prism_source_links`：

```ts
type PrismSourceLink = {
  id: string;
  source_type: "library_item" | "document" | "execution_output" | "manual_note";
  source_id: string;
  file_path: string;
  section_key?: string | null;
  quote?: string | null;
  citation_key?: string | null;
  usage: "cited" | "summarized" | "inspired" | "background";
};
```

迁移规则：

- 现有 metadata 中可识别的 file changes / applied changes / source usage 一次性迁入 canonical tables。
- 迁移完成后，runtime 不再双读 metadata。
- `LatexProject.llm_config.metadata` 只保留 editor/bridge 附属信息，不承载 product review / provenance 事实。

## 7. System Integration Points

### 7.1 Backend

| Area | Existing Entry | Adaptation |
| --- | --- | --- |
| Workspace Prism | `WorkspacePrismService` | 扩展 surface projection，聚合 review/context/activity |
| LaTeX bridge | `WorkspaceLatexProjectService` | 写入 canonical review/provenance/protected-section tables |
| Compute | `ComputeProjectionService` | 消费 `ResultReviewItem`，避免单独拼 Prism item |
| Commit | `ExecutionCommitService` | room commit 与 Prism apply 共享 review lifecycle |
| References | `ReferenceBibTeXService.sync_prism` / `PrismReviewService` | 同步 `refs.bib`，并从 review content 的 citation key 生成 source links |
| Activity | `WorkspaceActivityService` | 记录 Prism apply/reject/manual edit/compile events |
| Lead launch | `feature_launch_context` / `launch_feature` | 注入 manuscript projection、pending changes、protected sections |

### 7.2 Frontend

| Area | Existing Entry | Adaptation |
| --- | --- | --- |
| Workspace Prism route | `frontend/app/(workbench)/workspaces/[id]/prism/page.tsx` | 加载 product projection，处理 focus modes |
| Editor shell | `LatexEditorShell` | 暴露 apply/reject/manual edit events 给 workspace layer |
| Result UI | `CompletedView` / `ResultCard` | 统一消费 `ResultReviewItem` |
| Action routing | `frontend/lib/block-actions.ts` | 保持 Prism actions route 到 workspace surface，增加 review item focus |
| Rooms | Library / Documents / Decisions / Memory drawers | 支持从 Prism source link / decision link 反向打开 |
| Stores | `workspace-store` / `compute-store` | 缓存 lightweight Prism context，不复制 editor full state |

### 7.3 Agent Runtime

| Area | Adaptation |
| --- | --- |
| TaskBrief | 增加 manuscript context 摘要：outline、main files、protected sections、pending changes |
| TaskReport | 写作类 output 仍产出 proposed changes；explicit source-usage payload 属于后续扩展 |
| Lead runtime | 将 pending review items 和 protected sections 注入 subagent task inputs，避免 agent 对当前稿件状态失明 |
| Subagent skills | 写作 skill 明确输出 section-level proposed change，不直接声明“已写入” |

## 8. Implementation Slices (Closed)

### Slice 0: Canonical Schema and One-time Migration

Status: completed on branch `codex/workspace-prism-surface-impl`.

目标：先把 product truth 收进 canonical tables，避免后续功能继续长在 JSON metadata 或 frontend projection 上。

范围：

- 创建 `prism_review_items`
- 创建 `prism_source_links`
- 创建 `prism_protected_sections`
- 将现有 Prism file changes / applied changes 一次性迁入 `prism_review_items`
- 将可识别 source usage 一次性迁入 `prism_source_links`
- 移除 workspace-owned Prism runtime 对旧 metadata/file-change review state 的读取依赖

验收：

- runtime 只读 canonical Prism integration tables。
- `LatexProject.llm_config.metadata` 不再承载 review/provenance/protected-section product facts。
- migration 可重复 dry-run 校验，但正式运行后不保留双读 fallback。

### Slice 1: Prism Context Projection

Status: completed on branch `codex/workspace-prism-surface-impl`.

目标：让 Prism surface 能读到 workspace context，但不改变用户写作流。

范围：

- 扩展 `WorkspacePrismService.get_surface_projection`
- 加 `source_links / decisions / memory_preferences / recent_activity`
- 前端 Prism context rail 静态/只读展示
- 测试 projection 和 mobile layout

验收：

- Prism 页面能看到与稿件相关的 sources / decisions / activity。
- 没有关联数据时展示空态，不影响编辑器。

### Slice 2: Unified Review Item Contract

Status: completed on branch `codex/workspace-prism-surface-impl`.

目标：让 Workbench / ResultCard / Prism Changes tab 共享 DB-backed `ResultReviewItem`。

范围：

- 新增 backend presenter：canonical review rows -> review item projection
- CompletedView / ResultCard / Prism Changes tab 使用同一 review renderer
- `preview_prism_changes` 支持 focus 到具体 review item
- apply/reject/defer/revert 走同一 backend action contract

验收：

- 同一个 pending change 在 Workbench 和 Prism 里的标题、状态、diff、action 一致。
- accept/reject 后两边状态同步。

### Slice 3: Provenance and Source Links

Status: completed on branch `codex/workspace-prism-surface-impl`.

目标：让稿件变更知道“从哪里来”。

范围：

- Prism pending change 从 canonical pending content 与 workspace references 生成 source links
- review item projection 暴露 canonical source links
- Reference / Document detail 可从 Prism 反向打开
- apply 后写 activity

验收：

- 用户能从一个 Prism change 看到来源文献/文档/执行。
- apply 后 Run History / Activity 可追踪这次稿件改动。

### Slice 4: Manual Edit Feedback

Status: completed for protected sections and review activity; memory / decision candidates remain a post-merge product expansion and must still follow curated review.

目标：用户手改成为 future agent context。

范围：

- editor save/apply/reject/protect events
- canonical protected section rows
- memory / decision candidate prompt
- feature launch context 读取 protected sections

验收：

- 用户保护某段后，后续 agent 不直接覆盖该段。
- 用户保存的写作偏好能进入下一轮 TaskBrief。

### Slice 5: Agent-Aware Manuscript Launch

Status: completed on branch `codex/workspace-prism-surface-impl`.

目标：能力执行从一开始就知道当前稿件状态。

范围：

- `launch_feature` context 注入 manuscript projection
- writing capabilities 更新 prompt/brief schema
- pending changes 冲突提示
- context budget enforcement：只注入 lightweight projection
- tests 覆盖未确认变更时的行为

验收：

- 有 pending changes 时启动新写作任务，会提示先 review 或生成非覆盖型建议。
- agent 输出明确区分 proposed change 与 final manuscript state。

## 9. Success Criteria

产品层：

- 用户不再感觉 Prism 是另一个系统。
- 用户能从稿件变更追到来源、执行、决策。
- 用户在 Prism 里的选择会影响下一轮 agent 写作。

架构层：

- workspace-owned Prism 继续只通过 `/workspaces/:id/prism` 进入。
- `LatexProject` 仍只承担 manuscript storage/binding，不吞掉 room 数据。
- Compute / ResultCard / Prism review 不再维护三套 review state。
- Lead Agent 输出 proposed changes，不直接绕过用户审阅改稿。

工程层：

- Prism projection、review item、activity event 都有契约测试。
- E2E 覆盖 Workbench result -> Prism review -> apply -> Activity refresh。
- integrity report 继续保持 `missing_primary=[]`、`duplicate_primary=[]`。
- migration 后 runtime 不再从旧 metadata / payload 推断 workspace-owned Prism review 或 provenance。

## 10. Confirmed Architecture Decisions

1. `ResultReviewItem` 是 backend contract / DB-backed review state。
2. Provenance 首版直接建 canonical table，不走 `LatexProject.llm_config.metadata` 过渡。
3. 8 rooms 联动首阶段范围：Library / Documents / Decisions / Memory / Run History 深联动；Tasks / Sandbox / Settings 只做边界引用。
4. Manual edit feedback 以 section-level 为主；无法定位 section 时记录 `scope=file` 的同一 canonical event，不引入另一条 fallback path。
5. Manual edit 只能生成 memory / decision candidate，不能自动沉淀到 Memory / Decisions。
6. Agent launch context 只注入 lightweight manuscript projection，不注入全文。
7. 多稿件 / 多版本不在本阶段预留产品能力；`surface_role` 继续只承载 workspace primary manuscript 语义。
8. 不新增 workspace-owned Prism 的兼容层、runtime fallback、双写、双读或 frontend-only 事实源。

## 11. Implementation Closure

This overview has been executed. The current codebase now treats Prism as the Wenjin-native manuscript collaboration surface for a workspace.

Closed implementation scope:

1. Workspace-owned Prism route is canonical at `/workspaces/:id/prism`; historical standalone `/latex/:projectId` UI/page entry is removed.
2. Review state lives in canonical backend tables and is projected into Workbench result cards, completed view, Compute, and Prism Changes.
3. Source links, protected sections, and review activity are persisted as workspace facts rather than frontend-only state.
4. Lead execution receives lightweight manuscript context through `TaskBrief.manuscript_context`.
5. E2E covers Workbench result -> focused Prism review -> apply -> activity/context refresh -> room commit.

Post-merge product expansion, not required for this architecture closure:

1. Generate curated Memory / Decision candidates from repeated manual edits or rejections.
2. Broaden explicit TaskReport source-usage payloads beyond citation-derived source links.
3. Add production dashboards for stale legacy route hits, integrity report drift, and Prism apply/revert conflict rates.
