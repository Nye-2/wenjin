# Chat-first Workspace 功能落实规划

更新时间：2026-04-30
状态：Task A-F 已完成，后续进入功能收尾阶段
适用范围：`/home/cjz/wenjin`

本文是交给后续执行 agent 的功能落实任务书。它不改变当前核心架构主链路，而是在现有 `Chat -> FeatureIngress -> ExecutionSession/ComputeSession -> Task -> Feature runtime -> Artifact/Prism -> Chat summary` 基础上，把使用者心智收敛为：

```text
用户在 Workspace 里只需要持续和 Chat 对话。
Agent 在 Compute 中派发和执行工作，Compute 对用户是可观察但非必需操作的工作现场。
正式稿件和 LaTeX 工程进入 WenjinPrism，所有写入主稿的动作必须 preview/apply/revert。
```

## 0. 执行状态快照

截至 2026-04-30，本文中 Task A-F 对应的首轮 Chat-first 功能落实已经完成并通过验收：

1. `WorkspaceProjectStatusStrip` 已抽出并接入 Prism 状态。
2. Thread structured blocks 已拆分到 `thread-blocks/*`，覆盖 context、proposal、missing input、progress、result、failure、Prism status、next steps。
3. `WorkspaceThreadMessages` 已接入新 block 渲染和 `open_prism / preview_prism_changes / rerun_feature / resume_execution` 等 action。
4. Compute 可见文案已调整为 Agent 工作现场风格。
5. 后端 `thread_feature_cards.py` 已输出 `task_result`、`prism_status`、`task_failure`、`missing_input` 和 `next_steps`。
6. 相关前后端测试断言已更新。

后续不要重复实现 Task A-F。下一阶段按 [Workspace 功能完善收尾：下一阶段任务书](./workspace-functional-finalization-next-phase.md) 推进，重点是 action contract、Prism 写入确认、上传可引用状态、Semantic Scholar 文献资产沉淀和 release gate。

## 1. 关键产品假设

1. Workspace 类型下拉选择不是问题，保留现状。
2. `sci / thesis / proposal / software_copyright / patent` 是用户可以理解的交付类型，不需要重做创建入口。
3. Chat 是唯一主动操作入口。用户可以通过 Chat 发起、补充、确认、追问、修改、重试。
4. Compute 是 Agent 工作现场。用户可以看进度、材料、日志、产物，但不应该被要求在 Compute 内完成主流程操作。
5. Prism 是正式稿件中心。写作类产物不能只停在 artifact 或 chat 中，必须能进入 Prism 的 review gate。
6. Feature/Skill 是系统内部抽象。用户可以看到任务名称和下一步动作，但不应被迫理解 feature lifecycle。

## 2. 非目标

本轮不做：

1. 不重做 workspace type 选择器。
2. 不把 Compute 变成用户必须操作的主页面。
3. 不改 feature launch/resume 主链路。
4. 不新增 parallel feature execution 入口。
5. 不绕过 `FeatureIngressService`。
6. 不让 thread message 成为 feature 当前状态事实源。
7. 不把 Prism apply/revert 改成自动写入。
8. 不引入复杂多用户协作。
9. 不做完整 Claim-Evidence Graph，只为后续预留显示和 contract 位置。

## 3. 目标体验

用户进入 workspace 后，主路径应该是：

```text
打开 workspace
  -> 看见 Chat 和轻量项目状态
  -> 在 Chat 里说目标
  -> Chat 给出上下文理解 / 缺失信息 / 任务提案
  -> 用户确认或补充
  -> Agent 在 Compute 自动工作
  -> Chat 轻量显示任务进度
  -> 任务完成后 Chat 给结果摘要、产物去向、可信边界、下一步动作
  -> 写作结果进入 Prism 待确认写入
  -> 用户在 Chat 或 Prism 入口看到待处理修改
  -> 用户进入 Prism 预览、应用、编译或继续反馈修改
```

核心心智句：

```text
材料进 Workspace，任务从 Chat 发起，Agent 在 Compute 工作，正式稿进 Prism，下一步由 Chat 推荐。
```

## 4. 当前代码基线

执行 agent 应优先阅读以下文件：

### 4.1 前端主链

```text
frontend/app/(workbench)/workspaces/[id]/chat/page.tsx
frontend/app/(workbench)/workspaces/[id]/components/ThreadPanel.tsx
frontend/app/(workbench)/workspaces/[id]/components/WorkspaceThreadHeader.tsx
frontend/app/(workbench)/workspaces/[id]/components/WorkspaceThreadMessages.tsx
frontend/app/(workbench)/workspaces/[id]/components/WorkspaceThreadComposer.tsx
frontend/app/(workbench)/workspaces/[id]/components/WorkspaceInspector.tsx
frontend/components/compute/ComputeStage.tsx
frontend/components/compute/PrismPanel.tsx
frontend/stores/thread.ts
frontend/stores/compute.ts
frontend/stores/execution.ts
frontend/stores/workspace.ts
frontend/stores/dashboard.ts
frontend/lib/api/types.ts
frontend/lib/workspace-feature-action-context.ts
frontend/lib/workspace-feature-actions.ts
frontend/lib/workspace-feature-routes.ts
```

### 4.2 后端主链

```text
backend/src/application/presenters/thread_feature_cards.py
backend/src/application/presenters/thread_feature_presenters.py
backend/src/application/handlers/thread_turn_handler.py
backend/src/application/handlers/chat_turn_router.py
backend/src/application/handlers/feature_command_handler.py
backend/src/application/services/feature_launch_service.py
backend/src/compute/projection_service.py
backend/src/gateway/routers/thread_contracts.py
backend/src/gateway/routers/thread_serializers.py
backend/src/gateway/routers/compute.py
backend/src/workspace_features/registry.py
backend/src/workspace_features/runtime_profiles.py
backend/src/workspace_features/latex_sync.py
```

### 4.3 现有可复用基础

1. `ThreadPanel` 已有轻量状态条，可扩展为项目状态条。
2. `thread_feature_cards.py` 已有 `feature_proposal`、`task`、`warning`、`result`、`next_steps` blocks，可扩展为更明确的 Chat 任务卡片。
3. `ExecutionSession.next_actions` 已存在，可作为下一步动作来源之一。
4. `ComputeProjectionService` 已聚合 Prism metadata、tasks、artifacts、runtime blocks，可作为项目状态条和 Chat 结果卡片的数据源。
5. Prism file-change API 已有 `preview/apply/discard/revert`，不要重造写入机制。

## 5. 信息架构调整

### 5.1 Workspace 主屏

保持现有 Chat + Compute + Inspector 结构，但调整心智：

1. Chat 面板是主操作区。
2. Compute 面板文案改为 Agent 工作现场，不强调用户必须进入操作。
3. Inspector/侧边栏用于上下文浏览，不作为主流程入口。
4. Prism 入口在写作任务结果和项目状态中突出显示。

建议视觉层级：

```text
Workspace
  ├── Chat Panel（主）
  │     ├── Header
  │     ├── Project Status Strip
  │     ├── Messages with Task Cards
  │     └── Composer
  │
  ├── Agent Workbench / Compute（观察）
  │     ├── 当前任务
  │     ├── 阶段进度
  │     ├── 使用材料
  │     ├── Subagents / logs / artifacts
  │     └── Prism 状态摘要
  │
  └── Context Rail / Inspector（浏览）
        ├── 文献
        ├── 产物
        ├── Activity
        └── Knowledge
```

### 5.2 Chat 项目状态条

`ThreadPanel` 当前已有状态条，建议升级为 `WorkspaceProjectStatusStrip` 组件。

位置：

```text
frontend/app/(workbench)/workspaces/[id]/components/WorkspaceProjectStatusStrip.tsx
```

数据来源：

1. `workspace`：workspace name/type/discipline/config。
2. `dashboard.summary`：current phase、next step、headline。
3. `artifacts`：产物数量和最近产物。
4. `executionSessions`：是否有 running/awaiting_user_input/failed。
5. `compute projection`：Prism project id、pending file changes、applied file changes、compile status。
6. `workspace papers/literature`：如果当前 store 已有文献数量则展示；没有就先不阻塞。

最小展示字段：

```text
当前阶段：{currentPhaseTitle}
任务状态：无任务 / 运行中 / 等待补充 / 失败 / 已完成
主稿状态：未创建 / 已连接 Prism / 有待确认修改 / 编译通过 / 编译失败
产物：N 个
建议：{nextStepAction.title}
```

扩展展开态：

```text
项目摘要：dashboard headline 或 fallback 描述
当前任务：feature name + status + progress
主稿：Prism project + pending/applied changes
材料：artifacts count + paper/literature count
下一步建议：reason/description
```

验收标准：

1. 用户进入 workspace 后，不打开 Compute 也能知道当前是否有任务在跑。
2. 有 Prism 待确认修改时，状态条明显显示。
3. 有 awaiting_user_input execution 时，状态条提示“等待你补充信息”。
4. 状态条文案避免使用 `ExecutionSession`、`ComputeSession`、`feature_id` 等内部术语。

## 6. Chat 卡片体系

### 6.1 Block 类型规划

现有 `ThreadMessageBlock` 的 `type` 是字符串，前端应保持向后兼容：未知 block 继续 fallback。

建议新增或规范化以下 block：

```text
context_brief
task_proposal
missing_input
task_progress
task_result
task_failure
next_steps
prism_status
trust_signals
```

不要一次性强制所有后端路径都产出新 blocks。建议分阶段：

1. 先前端支持新 block renderer。
2. 后端 `thread_feature_cards.py` 渐进产出新 blocks。
3. 老 blocks 继续可渲染。

### 6.2 `context_brief`

用途：任务启动前说明系统将基于什么上下文执行，缺什么，输出会去哪里。

后端数据形状建议：

```json
{
  "type": "context_brief",
  "title": "本次任务上下文",
  "data": {
    "workspace_type": "sci",
    "feature_id": "writing",
    "will_use": [
      {"kind": "prism_project", "label": "当前主稿 main.tex", "count": 1},
      {"kind": "literature", "label": "工作区文献", "count": 12},
      {"kind": "artifact", "label": "论文框架与摘要", "count": 1}
    ],
    "missing": [
      {"field": "target_length", "label": "目标字数", "required": false}
    ],
    "output_destinations": [
      {"kind": "artifact", "label": "保存为章节草稿"},
      {"kind": "prism_file_change", "label": "生成 Prism 待确认写入"}
    ],
    "policy": {
      "will_not_overwrite_prism": true,
      "requires_review_gate": true
    }
  }
}
```

前端展示：

```text
我将使用：
- 当前主稿 main.tex
- 工作区文献 12 篇
- 论文框架与摘要

还缺：
- 目标字数（可选）

输出：
- 保存为章节草稿
- 生成 Prism 待确认写入
```

实施建议：

1. 第一阶段可以在前端根据 message metadata / orchestration / workspace stores 做弱推断。
2. 第二阶段后端从 `FeatureIngressService` 或 presenter 层产出真实 context brief。
3. 不要阻塞 launch。context brief 是降低不确定性，不是复杂表单。

### 6.3 `task_proposal`

用途：用户表达复杂目标后，Chat 提出要启动的任务。

现有 `feature_proposal` 可以兼容，建议前端将 `feature_proposal` 也按 task proposal 样式渲染。

数据形状建议：

```json
{
  "type": "task_proposal",
  "title": "建议启动「论文框架与摘要」",
  "data": {
    "feature_id": "framework_outline",
    "feature_name": "论文框架与摘要",
    "reason": "你已经提供论文主题，适合先生成摘要、关键词和章节结构。",
    "confidence": 0.82,
    "params": {
      "topic": "..."
    },
    "start_policy": "explicit_user_action"
  }
}
```

验收标准：

1. 用户可以从卡片明确知道系统要启动什么任务。
2. 卡片说明为什么适合这个任务。
3. 卡片有“启动任务”和“继续补充要求”。
4. 不出现“feature”作为主文案，除调试信息外。

### 6.4 `missing_input`

用途：缺参追问。

现有 `warning` + `next_steps` 可兼容，但建议新增明确 renderer。

数据形状建议：

```json
{
  "type": "missing_input",
  "title": "还缺少必要信息",
  "data": {
    "feature_id": "writing",
    "execution_session_id": "exec_xxx",
    "message": "请补充要写的章节类型或章节标题。",
    "missing_fields": [
      {"field": "section_type", "label": "章节类型", "examples": ["Introduction", "Related Work"]}
    ],
    "resume_policy": "reply_in_chat"
  }
}
```

验收标准：

1. 用户直接回复即可续跑，不需要进入 Compute。
2. 同一 execution session resume，不新建事务。
3. UI 明确提示“直接回复补充信息”。

### 6.5 `task_progress`

用途：让 Chat 也有轻量进度，不要求用户打开 Compute。

注意：不要把完整日志塞进 Chat。Chat 只显示摘要。

数据形状建议：

```json
{
  "type": "task_progress",
  "title": "Agent 正在处理",
  "data": {
    "feature_id": "literature_search",
    "execution_session_id": "exec_xxx",
    "task_id": "task_xxx",
    "status": "running",
    "phase": "筛选文献",
    "progress": 45,
    "message": "正在根据关键词和已有文献筛选高相关论文。",
    "compute_session_id": "compute_xxx"
  }
}
```

实施建议：

1. 第一阶段不必实时往 thread 追加 progress messages。
2. 前端可在最新 task block 上结合 execution store 显示动态状态。
3. 后端完成态仍写 thread summary。

验收标准：

1. 用户在 Chat 中能看到任务已经启动。
2. 用户不打开 Compute 也知道是否运行中、等待输入、失败、完成。
3. Compute 仍是详细过程查看入口。

### 6.6 `task_result`

用途：任务完成后的标准收口。

数据形状建议：

```json
{
  "type": "task_result",
  "title": "论文框架与摘要已完成",
  "data": {
    "feature_id": "framework_outline",
    "execution_session_id": "exec_xxx",
    "summary": "已生成摘要、关键词和 6 个章节结构。",
    "destinations": [
      {"kind": "artifact", "label": "论文框架与摘要", "id": "artifact_xxx"},
      {"kind": "prism", "label": "WenjinPrism 主稿", "project_id": "latex_xxx"}
    ],
    "prism": {
      "project_id": "latex_xxx",
      "url": "/latex/latex_xxx",
      "pending_file_changes": 2,
      "applied_file_changes": 0,
      "compile_status": "not_compiled"
    },
    "trust": {
      "used_context_count": 3,
      "unverified_items": 2,
      "citation_status": "needs_review",
      "will_not_overwrite_prism": true
    }
  }
}
```

前端展示必须包含：

1. 完成摘要。
2. 产物保存在哪里。
3. 是否有 Prism 待确认写入。
4. 是否存在待核验内容。
5. 下一步动作。

### 6.7 `task_failure`

用途：长任务失败后的恢复入口。

数据形状建议：

```json
{
  "type": "task_failure",
  "title": "任务在生成草稿阶段失败",
  "data": {
    "feature_id": "literature_review",
    "execution_session_id": "exec_xxx",
    "task_id": "task_xxx",
    "failed_phase": "生成 Related Work 草稿",
    "error_summary": "模型输出未能解析为 JSON。",
    "completed": [
      "已完成文献筛选",
      "已完成主题聚类"
    ],
    "not_applied": true,
    "prism_affected": false,
    "recovery_actions": [
      {"label": "基于已完成结果重试", "action": "resume"},
      {"label": "缩短目标字数后重试", "action": "continue_thread"},
      {"label": "换模型重试", "action": "rerun_with_model"}
    ]
  }
}
```

验收标准：

1. 失败后用户知道 Prism 是否受影响。
2. 失败后用户能在 Chat 里重试或补充，不需要进入 Compute。
3. 有可复用中间结果时明确显示。

### 6.8 `prism_status`

用途：把 Prism 的正式稿状态带回 Chat。

数据形状建议：

```json
{
  "type": "prism_status",
  "title": "主稿状态",
  "data": {
    "project_id": "latex_xxx",
    "project_name": "Untitled Paper",
    "main_file": "main.tex",
    "pending_file_changes": 2,
    "applied_file_changes": 1,
    "compile_status": "blocked_by_review",
    "actions": [
      {"label": "打开 WenjinPrism", "kind": "open_prism", "url": "/latex/latex_xxx"},
      {"label": "查看待确认修改", "kind": "open_prism_changes", "url": "/latex/latex_xxx"}
    ]
  }
}
```

验收标准：

1. 写作类任务完成后，Chat 中能看到是否有待确认写入。
2. 用户不需要去 Compute 找 Prism 状态。
3. 进入 Prism 的入口明确。

## 7. 后端实施计划

### 7.1 扩展 thread card presenter

目标文件：

```text
backend/src/application/presenters/thread_feature_cards.py
backend/src/application/presenters/thread_feature_presenters.py
```

任务：

1. 保留现有 block 类型。
2. 新增 helper：

```python
def _build_context_brief_block(...): ...
def _build_task_result_block(...): ...
def _build_task_failure_block(...): ...
def _build_prism_status_block(...): ...
def _build_trust_signals_block(...): ...
```

3. `build_feature_started_response` 或等价启动响应中补充：
   - task block
   - optional context brief
   - next steps
4. `build_feature_completed_response` 或等价完成响应中补充：
   - task_result
   - prism_status when `latex_project_id` or `file_changes` exists
   - next_steps
5. `build_missing_response` 输出 `missing_input` block，同时保留 warning block 或兼容旧 renderer。
6. feature result summary 增强 destinations/trust/prism。

注意：

1. presenter 不应该直接查大量数据库。
2. 优先使用 feature result data、artifacts、execution metadata 和已传入 payload。
3. 如果缺少信息，就返回保守字段，不要阻塞任务完成。

验收：

1. 后端单测覆盖每类 block 的结构。
2. 旧前端即使不识别新 block，也能看到 content 文本。
3. 新前端能识别新 block 并渲染卡片。

### 7.2 标准化 next actions

目标文件：

```text
backend/src/workspace_features/registry.py
backend/src/application/presenters/thread_feature_presenters.py
backend/src/application/presenters/thread_feature_cards.py
frontend/lib/workspace-feature-actions.ts
frontend/lib/workspace-feature-action-*.ts
```

建议统一 action kind：

```text
continue_thread
trigger_feature
open_prism
preview_prism_changes
open_artifact
open_literature
rerun_feature
resume_execution
create_feedback
```

数据形状：

```json
{
  "label": "写 Introduction",
  "kind": "trigger_feature",
  "feature_id": "writing",
  "params": {
    "section_type": "introduction"
  },
  "requires_confirmation": true,
  "disabled_reason": null
}
```

原则：

1. next actions 是用户语言，不暴露 handler_key。
2. 如果 action 不能直接执行，必须给 `disabled_reason`。
3. 对 Prism 动作使用 `project_id/url`，不要伪造成 feature。

### 7.3 失败恢复响应

目标文件：

```text
backend/src/application/handlers/thread_turn_handler.py
backend/src/application/handlers/feature_command_handler.py
backend/src/task/handlers/workspace_feature_handler.py
backend/src/services/execution_session_service.py 或现有 execution service
```

任务：

1. 确认 feature task failed 后是否会写回 assistant summary。
2. 如果已有失败摘要，扩展为 `task_failure` block。
3. 从 `ExecutionSession.last_error`、`TaskRecord.error`、`runtime_snapshot.current_phase` 提取失败阶段。
4. 如果 Prism 没有 applied changes，明确 `prism_affected=false`。
5. 如果有 artifact_ids，显示已生成中间产物。

验收：

1. 模拟 feature failed，Chat 显示失败恢复卡。
2. 用户可从 Chat 触发 retry/resume 或继续补充。
3. 失败不会误导用户以为主稿已改。

### 7.4 Requirements 最小模型

这是第二阶段任务，不建议第一阶段阻塞 Chat 卡片化。

最小实现建议先放在 `Workspace.config`，避免过早新增表：

```json
{
  "requirements": [
    {
      "id": "req_xxx",
      "kind": "journal_guideline",
      "title": "目标期刊要求",
      "content": "摘要不超过 250 words...",
      "source": "user",
      "status": "active",
      "created_at": "..."
    }
  ]
}
```

后续可迁移为独立表。

后端 API 可复用 workspace update，或新增：

```text
GET /api/workspaces/{workspace_id}/requirements
POST /api/workspaces/{workspace_id}/requirements
PATCH /api/workspaces/{workspace_id}/requirements/{requirement_id}
DELETE /api/workspaces/{workspace_id}/requirements/{requirement_id}
```

第一阶段只需要前端展示占位和 Chat 文案预留，不必完整实现 CRUD。

## 8. 前端实施计划

### 8.1 项目状态条组件化

新增：

```text
frontend/app/(workbench)/workspaces/[id]/components/WorkspaceProjectStatusStrip.tsx
```

从 `ThreadPanel.tsx` 中抽出当前状态条逻辑。

Props 建议：

```ts
interface WorkspaceProjectStatusStripProps {
  workspaceId: string;
  workspaceName?: string | null;
  workspaceType?: string | null;
  currentPhaseTitle: string;
  currentPhaseDescription: string;
  activeSkillLabel?: string | null;
  artifactsCount: number;
  activeExecution: ExecutionSession | null;
  nextStepAction: {
    title: string;
    description?: string | null;
    reason?: string | null;
  } | null;
}
```

第二阶段再加入：

```ts
prismStatus?: {
  projectId?: string | null;
  pendingFileChanges: number;
  appliedFileChanges: number;
  compileStatus?: string | null;
};
materialsStatus?: {
  literatureCount?: number;
  coreLiteratureCount?: number;
};
```

UI 要求：

1. 单行紧凑展示，不占据太多聊天空间。
2. 展开态展示详情。
3. running/awaiting/failed 状态有清楚颜色和文本。
4. 文案使用“Agent 正在工作”“等待你补充”“主稿有待确认修改”，不要使用内部术语。

### 8.2 Chat block renderer

目标文件：

```text
frontend/app/(workbench)/workspaces/[id]/components/WorkspaceThreadMessages.tsx
```

建议拆分新文件：

```text
frontend/app/(workbench)/workspaces/[id]/components/thread-blocks/ContextBriefBlock.tsx
frontend/app/(workbench)/workspaces/[id]/components/thread-blocks/TaskProposalBlock.tsx
frontend/app/(workbench)/workspaces/[id]/components/thread-blocks/MissingInputBlock.tsx
frontend/app/(workbench)/workspaces/[id]/components/thread-blocks/TaskProgressBlock.tsx
frontend/app/(workbench)/workspaces/[id]/components/thread-blocks/TaskResultBlock.tsx
frontend/app/(workbench)/workspaces/[id]/components/thread-blocks/TaskFailureBlock.tsx
frontend/app/(workbench)/workspaces/[id]/components/thread-blocks/PrismStatusBlock.tsx
frontend/app/(workbench)/workspaces/[id]/components/thread-blocks/NextStepsBlock.tsx
frontend/app/(workbench)/workspaces/[id]/components/thread-blocks/index.ts
```

如果不想一次性拆太多，可先在 `WorkspaceThreadMessages.tsx` 内实现 renderer，再后续拆分。

渲染映射：

```ts
switch (block.type) {
  case "context_brief":
    return <ContextBriefBlock ... />;
  case "feature_proposal":
  case "task_proposal":
    return <TaskProposalBlock ... />;
  case "missing_input":
  case "warning":
    return <MissingInputBlock ... />;
  case "task":
  case "task_progress":
    return <TaskProgressBlock ... />;
  case "result":
  case "task_result":
    return <TaskResultBlock ... />;
  case "task_failure":
    return <TaskFailureBlock ... />;
  case "prism_status":
    return <PrismStatusBlock ... />;
  case "next_steps":
    return <NextStepsBlock ... />;
  default:
    return <GenericBlock ... />;
}
```

### 8.3 Chat action handling

目标文件：

```text
frontend/app/(workbench)/workspaces/[id]/components/WorkspaceThreadMessages.tsx
frontend/lib/workspace-feature-routes.ts
frontend/lib/workspace-feature-actions.ts
frontend/lib/workspace-feature-action-context.ts
```

动作处理原则：

1. `trigger_feature`：通过现有 chat route + orchestration metadata 启动，不直接绕过 ingress。
2. `continue_thread`：把建议 prompt 填入 composer 或直接发送，优先填入 composer 避免误触。
3. `open_prism`：路由到 `/latex/{project_id}`。
4. `preview_prism_changes`：路由到 Prism，并尽量定位 pending changes；第一阶段可以只打开 Prism。
5. `open_artifact`：打开 activity/artifact detail 或现有 artifact 面板。
6. `rerun_feature` / `resume_execution`：必须携带 execution_session_id 或 params，避免新建错误任务。

验收：

1. 用户点击 task result 的下一步按钮，可以继续在 Chat 里推进。
2. Prism 动作不会启动新的 feature。
3. 不支持的动作显示 disabled reason。

### 8.4 Compute 文案调整

目标文件：

```text
frontend/components/compute/ComputeStage.tsx
frontend/components/compute/ComputeHeader.tsx
frontend/components/compute/PrismPanel.tsx
frontend/components/compute/SubagentPanel.tsx
frontend/components/compute/TaskArtifactPanel.tsx
frontend/components/compute/LogPanel.tsx
frontend/components/compute/ReviewGatePanel.tsx
```

目标：

1. 对用户展示为“Agent 工作现场”或“Agent Workbench”。
2. 保留代码和 API 命名为 Compute，不做大规模重命名。
3. 默认文案强调“这里展示 Agent 的工作过程，不需要你手动操作”。
4. 操作按钮保留但弱化。主流程操作从 Chat/Prism 进入。

示例替换：

```text
Compute 工作面 -> Agent 工作现场
启动 feature 后 -> 启动任务后
runtime blocks -> 工作过程
subagents -> 协作 Agent
review gate -> 写入/质量检查
```

验收：

1. 用户看到 Compute 不会误以为必须进去操作。
2. 高级用户仍能展开日志、查看 subagents、查看产物。

### 8.5 Prism 状态回到 Chat

目标：

1. 写作类 feature 完成后，Chat result card 显示 Prism project、pending changes、open Prism。
2. 状态条显示 pending file changes 数量。
3. 如果 compile blocked by review，Chat/状态条说明“有待确认修改，暂不编译新 PDF”。

数据来源：

1. `feature result data.latex_project_id`
2. `feature result data.prism_url`
3. `feature result data.file_changes`
4. `compute projection.prism`
5. `LatexProject.llm_config.metadata.file_changes`

前端容错：

1. 如果只有 `latex_project_id`，也能显示打开 Prism。
2. 如果没有 pending count，不显示数量。
3. 如果没有 Prism project，不显示 Prism block。

## 9. 分阶段交付

### Phase 1：Chat 任务卡片和状态条

目标：不改变后端主链路的情况下，让用户在 Chat 中理解任务状态、结果和下一步。

范围：

1. 抽出 `WorkspaceProjectStatusStrip`。
2. 前端支持新旧 task/proposal/result/next_steps block renderer。
3. 扩展 `thread_feature_cards.py`，完成态输出更丰富的 `task_result` 和 `prism_status`。
4. Feature 启动和缺参场景文案用户化。
5. Compute 空状态文案改为 Agent 工作现场。

验收：

1. 发起一个 SCI writing 或 framework outline，Chat 中能看到任务卡、完成卡、下一步动作。
2. 任务运行时，状态条显示运行中。
3. 任务完成后，状态条恢复并显示下一步建议。
4. 不打开 Compute 也能理解任务是否完成。
5. TypeScript 检查通过。

建议测试：

```bash
cd frontend
npm run typecheck
```

如果没有 `typecheck` script：

```bash
cd frontend
npx tsc --noEmit
```

后端：

```bash
cd backend
uv run pytest tests/application tests/gateway/routers/test_features.py
```

### Phase 2：Prism 主稿闭环显性化

目标：写作类产物进入 Prism 的状态在 Chat 可见。

范围：

1. 后端 task result block 增加 Prism destination/trust fields。
2. 前端 `PrismStatusBlock`。
3. 状态条显示 pending/applied file changes。
4. Chat next action 支持 open_prism / preview_prism_changes。
5. Compute 的 PrismPanel 操作保留，但不作为主流程唯一入口。

验收：

1. 写作 feature 完成后，Chat 中出现“打开 WenjinPrism”。
2. 有 file_changes 时，Chat 中显示“待确认修改”。
3. 用户点击后进入对应 Prism project。
4. 未经 apply 不覆盖主稿。

### Phase 3：上下文确认和 Requirements 最小入口

目标：启动任务前让用户知道系统会用什么材料、遵守什么要求。

范围：

1. `ContextBriefBlock` 前端渲染。
2. 后端 presenter 生成保守 context brief。
3. Workspace config 中支持 requirements 最小结构。
4. UI 侧边或状态展开态显示 requirements 摘要。
5. Chat 支持用户自然语言添加 requirement 的最小路径，可先由 lead-agent 回答并提示保存，后续再自动结构化。

验收：

1. 用户启动写作任务前能看到本次使用的材料摘要。
2. 用户能看到“不会自动覆盖主稿”的提示。
3. 用户能把期刊/导师/模板要求保存到 workspace context。

### Phase 4：失败恢复

目标：长任务失败后，用户可从 Chat 继续。

范围：

1. 后端失败态生成 `task_failure` block。
2. 前端 `TaskFailureBlock`。
3. 支持 retry/resume/continue_thread 三类恢复动作。
4. 显示 Prism 是否受影响。

验收：

1. 模拟 feature 失败，Chat 显示失败阶段和恢复动作。
2. 用户可点击重试或继续补充。
3. 不产生重复写入 Prism。

## 10. 具体任务拆分给执行 agent

建议按以下顺序提交，避免大 PR 难 review。

### Task A：前端状态条组件化

修改文件：

```text
frontend/app/(workbench)/workspaces/[id]/components/ThreadPanel.tsx
frontend/app/(workbench)/workspaces/[id]/components/WorkspaceProjectStatusStrip.tsx
```

要求：

1. 从 `ThreadPanel` 抽出当前 status strip。
2. 保持现有行为不退化。
3. 文案改成用户语言。
4. 加入 active execution status、artifacts count、next step。

验收：

```bash
cd frontend && npx tsc --noEmit
```

### Task B：前端 Chat cards renderer

修改文件：

```text
frontend/app/(workbench)/workspaces/[id]/components/WorkspaceThreadMessages.tsx
frontend/app/(workbench)/workspaces/[id]/components/thread-blocks/*
```

要求：

1. 支持 `context_brief/task_proposal/missing_input/task_progress/task_result/task_failure/prism_status/next_steps`。
2. 兼容旧 `feature_proposal/task/warning/result/next_steps`。
3. 所有 action button 必须经过现有 route/orchestration helper，不绕过 Chat。
4. 未知 block fallback。

验收：

1. 现有历史消息仍可渲染。
2. 新 blocks mock 数据可渲染。
3. TypeScript 通过。

### Task C：后端完成态卡片增强

修改文件：

```text
backend/src/application/presenters/thread_feature_cards.py
backend/src/application/presenters/thread_feature_presenters.py
```

要求：

1. 新增 `task_result` block。
2. 如果 result data 包含 `latex_project_id/prism_url/file_changes/applied_file_changes/compile_status`，新增 `prism_status` block。
3. `next_steps` 增加 open_prism 或 preview_prism_changes。
4. content 文本仍可独立阅读。

验收：

1. 添加或更新 presenter 单测。
2. 后端相关测试通过。

### Task D：Compute 文案轻量改造

修改文件：

```text
frontend/components/compute/ComputeStage.tsx
frontend/components/compute/ComputeHeader.tsx
frontend/components/compute/*.tsx
```

要求：

1. 用户可见文案从 Compute 术语改为 Agent 工作现场。
2. 不重命名 API、store、组件导出。
3. 空状态明确说明“不需要手动操作，这里展示 Agent 工作过程”。

验收：

1. 页面无布局破坏。
2. TypeScript 通过。

### Task E：Prism 状态进入 Chat 和状态条

修改文件：

```text
frontend/app/(workbench)/workspaces/[id]/components/WorkspaceProjectStatusStrip.tsx
frontend/app/(workbench)/workspaces/[id]/components/thread-blocks/PrismStatusBlock.tsx
frontend/stores/compute.ts 或现有 selector helper
backend/src/application/presenters/thread_feature_cards.py
```

要求：

1. 从 compute projection 或 result block 中显示 pending file changes。
2. Chat result card 可打开 Prism。
3. 有 pending changes 时状态条显示。

验收：

1. 写作类任务完成后，Chat 和状态条都能看到 Prism 状态。
2. 点击可打开 `/latex/{projectId}`。

### Task F：失败恢复卡片

修改文件：

```text
backend/src/application/presenters/thread_feature_cards.py
backend/src/application/handlers/feature_command_handler.py
frontend/app/(workbench)/workspaces/[id]/components/thread-blocks/TaskFailureBlock.tsx
```

要求：

1. 失败时生成 `task_failure`。
2. 前端展示失败阶段、已完成内容、Prism 是否受影响、恢复动作。
3. 恢复动作回到 Chat。

验收：

1. 模拟失败路径可见。
2. 无重复 task 或绕过 ingress。

## 11. 设计约束

1. Chat 是主动入口，所有启动和续跑都应通过 Chat orchestration 或 canonical feature API adapter，不能由卡片直接调用 graph/task handler。
2. Compute 只能观察和展示，保留必要高级操作，但不要让它成为主流程唯一入口。
3. Prism 写入必须继续走 preview/apply/discard/revert。
4. 所有 blocks 必须能在缺字段时优雅降级。
5. 前端不得从 thread message 反推 feature 当前事实状态；当前状态仍以 execution/task/compute projection 为准。
6. 新 block 类型必须向后兼容旧消息。
7. 用户文案中尽量避免 `feature`、`execution session`、`compute session`、`runtime snapshot`。
8. 内部代码命名可以保留现有架构词，不做无收益大重命名。

## 12. 验收场景

执行 agent 完成后，至少手动或自动验证以下路径。

### 12.1 SCI 文献检索到下一步

流程：

```text
创建/进入 SCI workspace
在 Chat 输入：帮我围绕 XXX 做一轮文献检索并找 research gap
确认任务启动
等待完成
查看 Chat result card
点击下一步：生成论文框架或 Related Work
```

预期：

1. Chat 有任务提案/启动/完成卡。
2. Compute 可观察过程，但不必操作。
3. 完成卡显示产物和下一步。

### 12.2 SCI 框架写入 Prism

流程：

```text
在 Chat 输入：基于当前主题生成论文框架和摘要
任务完成
查看 Chat result card
打开 Prism
查看 pending file changes
```

预期：

1. Chat 显示 Prism project。
2. 有待确认写入时显示数量。
3. 未 preview/apply 不覆盖主稿。

### 12.3 缺参续跑

流程：

```text
在 Chat 输入：帮我写一节
系统提示缺章节信息
用户回复：写 Introduction，英文，约 800 words
同一 execution session 续跑
```

预期：

1. Missing input card 显示最少缺失字段。
2. 用户直接回复即可继续。
3. 不重复创建无关任务。

### 12.4 失败恢复

流程：

```text
人为让某个 feature 失败
查看 Chat failure card
点击重试或继续补充
```

预期：

1. 失败阶段清晰。
2. 显示已完成内容。
3. 显示 Prism 未受影响或受影响状态。
4. 恢复动作不绕过 ingress。

## 13. 建议测试命令

前端：

```bash
cd frontend
npx tsc --noEmit
```

后端：

```bash
cd backend
uv run pytest tests/application tests/gateway/routers/test_features.py
```

如果改到 compute/projection：

```bash
cd backend
uv run pytest tests
```

如测试环境缺依赖，执行 agent 必须在最终说明中明确哪些命令未能运行，以及阻塞原因。

## 14. 最终交付标准

本规划完成后，用户应形成稳定心智：

1. 我在 Chat 里描述目标即可。
2. Agent 会在工作现场自动处理，我可以看但不用操作。
3. Chat 会告诉我任务是否启动、运行、完成或失败。
4. Chat 会告诉我产物在哪里。
5. 正式稿件进入 Prism，不会被偷偷覆盖。
6. 每次完成后系统会给出下一步。
7. 出错后可以在 Chat 里恢复。

如果一个新用户完成“调研 -> 框架 -> 章节草稿 -> Prism 待确认写入”路径时不需要理解 Compute、ExecutionSession、FeatureIngress 等内部概念，则本轮改进达标。
