# Chat 体验重设计 · 设计文档

- **日期**：2026-05-07
- **作者**：ze + Claude（superpowers brainstorming）
- **状态**：待 review，dev 阶段无用户、彻底重构无 fallback
- **范围**：`/workspaces/[id]/chat` 的左右两栏 UI、agent 输出协议、关键 backend prompt、暂停/错误/持久化机制

---

## 1. 背景与动机

### 1.1 用户体验症状

实测一条最常见路径：用户输入「我想写一篇论文，联邦学习结合大模型方向」，agent 回复中暴露出多类问题：

1. **内部 taxonomy 泄露**：消息里出现 `message_feature_proposal`、`意图置信度 60%` 这类 debug/分类 token
2. **重复按钮**：「启动论文分析」「先继续补充要求」在同一条消息里出现 2 次
3. **自我汇报**：agent 用一段话解释自己接下来要做什么（"我会先复用当前工作区、线程上下文和已有产物..."），而不是去做
4. **不会提问**：用户给了具体研究方向，agent 没追问任何对推进有用的问题
5. **右面板 4 tab（成果 / 工作 / 来源 / 活动）信息密度高、层次不清**，不知道哪里是主入口
6. **看不到运行结果**：agent 跑完最终输出在哪、不明确
7. **滚动困难**：右面板像是不能上下滑动

### 1.2 根因分析

- 症状 1–4：lead_agent 的 system prompt 把内部分类元数据 + 元话术 + 自由 button 提议混在自由文本里输出，前端没有结构化 schema 约束
- 症状 5：右面板设计成了 4 个并列 tab，没有"主面板 + 辅面板"的层级
- 症状 6：最终结果只沉到右面板成果 tab，chat 闭环不完整
- 症状 7：可能是 CSS overflow 问题，也可能是没有清晰的"自动跟随当前进度"行为

### 1.3 设计目标

把 chat 重做成"action-first agent + brainstorming-style 提问 + 可见可逆的 run 闭环"，并把右面板做成 langgraph subagent 真实拓扑的实时工作台。

---

## 2. 操作原则（设计约束、按优先级）

1. **不泄露内部 token** —— agent 输出里不出现 `message_feature_proposal`、置信度、turn 编号、graph 节点名
2. **不自我汇报** —— 不说"我会先复用工作区、线程上下文..."；要做就直接做
3. **chat 是对话，右面板是工坊** —— 过程信息只去右面板；chat 只承载人话 + 关键节点（status_line / question_card / result_card）
4. **岔路才问，问就一个** —— brainstorming 风格，single focused question + 0–3 pill 建议；同 thread 同时最多 1 个未回答 question_card
5. **每一轮都有结尾** —— 每个 run 终止于 result_card，不留开放式中断；用户可对 result 反馈/迭代/推翻

---

## 3. 架构总览

### 3.1 改动层级

| 层 | 改 | 不改 |
|---|---|---|
| 前端组件 | 替换 `WorkspaceInspector` / `ComputeStage` / `ThreadPanel` / `WorkspaceThreadMessages` 主体 + 删除 `thread-blocks/*` 中除 text 外的全部历史 block 类型 | `proxy.ts`、SSE 客户端 `subscribeJsonEventStream`、`WorkspaceThreadComposer` 的文件上传能力 |
| Backend chat 协议 | 引入 4 类结构化 `AgentBlock`，agent 用 LangChain `with_structured_output` 输出；新增 `workspace_run` 持久化表 | SSE 传输路径、`subagent.updated` event payload schema |
| Backend prompt | 重写 lead_agent system prompt + 各 skill `guidance_prompt`，移除 jargon + 自我汇报话术，注入 4 类 block 输出格式约束 | langgraph 拓扑、`ParallelExecutor`、`GlobalSubagentManager` 的核心调度（仅加 pause hook） |

### 3.2 不动 langgraph 的关键依据

`subagent.updated` event payload 已经包含 `workflow_phase` / `workflow_phase_index` / `workflow_task_index` / `subagent_type` / `output_preview` / `token_usage` / `model_name` / `status` 全部字段。前端 `LiveWorkflowPanel` 直接消费，无需后端拓扑改动。

---

## 4. 前端组件设计

### 4.1 右面板 · `LiveWorkflowPanel`

```
LiveWorkflowPanel  (订阅 workspace SSE 'subagent.updated' 流)
├─ Header           当前 task 标题 + 总耗时 + 总 token + [在下个安全点暂停] 按钮
├─ RunList
│  └─ Run[]
│     ├─ RunHeader   "轮 N · 标题 · 状态"  ← 完成后整体可折叠
│     └─ PhaseList   仅当前 run 默认展开
│        └─ Phase[]                          按 workflow_phase_index 分组
│           ├─ PhaseHeader   ✓/◐/idx · 标题 · summary · 折叠箭头
│           └─ SubagentGrid  done 折叠 / running 展开（二级折叠，phase 内 subagent 数 ≥ 6 时启用）
│              └─ SubagentCard[]            2 列 grid（phase 内 1 个时退化整行）
│                 ├─ status pill            pending/running/done/waiting/failed
│                 ├─ subagent_type 小字
│                 ├─ output_preview         流式更新（last 1-2 lines）
│                 └─ token / 耗时 角标
├─ WorkspaceAssets  折叠区，承担原 ArtifactLibrary / LiteraturePanel / KnowledgePanel
│  ├─ Tab: 成果      ArtifactLibrary（可点开预览/下载/归档）
│  ├─ Tab: 文献      LiteraturePanel（搜索/上传/分类）
│  └─ Tab: 上下文    KnowledgePanel（workspace 上下文片段）
└─ Footer           汇总 + 自动滚动指示
```

**默认行为**：
- 没有 active run：`WorkspaceAssets` 默认展开（让用户看到沉淀物），上面的 RunList 折叠成历史列表
- 有 active run：`WorkspaceAssets` 默认折叠成一行入口（"📚 文献(12) · 📦 成果(3) · 🧠 上下文"），RunList 主区展开

**字段绑定**（来自 `subagent.updated` event）：
- `subagent.task_id` → `SubagentCard` key
- `subagent.workflow_phase_index` → 分组到 `Phase`
- `subagent.workflow_task_index` → grid 内排序
- `subagent.status` → 状态 pill
- `subagent.output_preview` → 流式预览
- `subagent.token_usage` / `model_name` → 角标
- `subagent.subagent_type` → 卡名标签
- `subagent.metadata.criticality` → 决定失败时的呈现严重度（参见 §6.3）

**关键交互**：
- 用户上滑 → 暂停 auto-follow；浮按钮"回到当前进度"出现
- 点 `PhaseHeader` → 折叠/展开（已完成默认折叠、当前默认展开）
- 点 `SubagentCard "需要你回答"` → 自动跳到 chat 中对应 `question_card`
- 点 Header「暂停」→ 调用 `POST /workspaces/{id}/runs/{run_id}/pause`，参见 §6.1

### 4.2 左面板 · `ChatThread`

```
ChatThread
├─ EmptyState         (仅当 thread 无任何 message 时显示)
│  ├─ feature 简介
│  ├─ 3 条 starter prompts (来自 feature.guidancePrompt 头部)
│  └─ 输入框 placeholder 提示
├─ MessageList
│  ├─ UserMessage
│  └─ AgentMessage
│     └─ Block[]      (单条 message 可包含多个 block，按数组顺序渲染)
│        ├─ TextBlock
│        ├─ StatusLineBlock      "→ phase 1 完成 · 启动 phase 2"  click → 跳右面板
│        ├─ QuestionCardBlock    question + 0-3 pills + 自由输入
│        └─ ResultCardBlock      TL;DR + findings + recommend + links + 反馈区
└─ InputArea  (= WorkspaceThreadComposer 重新接入)
   ├─ 文本输入
   ├─ 文件上传 (literature / workspace_context / transient — 沿用现有能力)
   └─ [中断当前任务] 按钮（在 active run 期间显示）
```

**Run 折叠规则**：
- 一个 thread 内可以有多个 run（用户对 result_card 反馈触发新 run）
- 已完成 run 的 message 整体包成 `RunContainer`，折叠成单行 `轮 N · 标题 ✓ ▾`
- 当前 run 始终展开
- 折叠状态保存在 `useWorkflowStore.collapsedRunIds`

**Block focus 行为**：
- 当一个 message 包含 `QuestionCardBlock` 或 `ResultCardBlock`，自动滚动到该 block 并加视觉高亮 1.5s
- 输入框 placeholder 切换：默认 → 「直接说想法...」（出现 question_card 时）→ 「或对结果反馈、推翻、迭代」（出现 result_card 时）

### 4.3 状态管理

新建 `useWorkflowStore` (zustand)：

```ts
interface WorkflowStore {
  runs: Run[]                       // 当前 thread 下所有 run，按时间顺序
  currentRunId: string | null
  pausedRunIds: Set<string>
  followCurrent: boolean            // 自动滚到当前 phase
  collapsedPhaseIds: Set<string>
  collapsedRunIds: Set<string>

  // actions
  upsertSubagentEvent(ev: WorkspaceSubagentUpdatedEvent): void
  toggleRun(runId: string): void
  togglePhase(phaseId: string): void
  setFollow(enabled: boolean): void
  pauseRun(runId: string): Promise<void>
  resumeRun(runId: string): Promise<void>
  deleteRun(runId: string): Promise<void>
}
```

**替换**：现有的 `useExecutionStore` 和 `useWorkspaceStore.activities` 中与 run/subagent 相关部分。

**审计任务**（前置必做）：grep `useExecutionStore` 所有引用点，迁移完毕后才能删除。这条作为实施计划 Phase 0。

---

## 5. Backend 协议

### 5.1 `AgentBlock` schema

Pydantic 模型（路径：`backend/src/agents/lead_agent/blocks.py`）：

```python
from pydantic import BaseModel, Field
from typing import Literal, Optional

class TextBlock(BaseModel):
    kind: Literal["text"] = "text"
    content: str

class StatusLineBlock(BaseModel):
    kind: Literal["status_line"] = "status_line"
    label: str                                    # i18n key 或字面值
    run_id: str
    phase_index: Optional[int] = None
    tone: Literal["info", "warn", "error"] = "info"

class Pill(BaseModel):
    label: str
    intent: str                                    # 用户点击后给 agent 的 directive

class QuestionCardBlock(BaseModel):
    kind: Literal["question_card"] = "question_card"
    label: str                                     # "需要你拍一下"
    question: str
    pills: list[Pill] = Field(default_factory=list, max_length=3)
    context_ref_subagent_task_id: Optional[str] = None
    context_ref_phase_index: Optional[int] = None

class Finding(BaseModel):
    id: str                                        # ① ② ③ 用作引用
    text: str

class Recommend(BaseModel):
    label: str
    body: str

class Link(BaseModel):
    icon: str
    label: str
    href: str                                      # 内部路由或外部 url

class FeedbackPill(BaseModel):
    kind: Literal["primary", "normal", "warn"]
    label: str
    intent: str

class FeedbackBlock(BaseModel):
    question: str
    pills: list[FeedbackPill]
    allow_free_input: bool = True

class RunStats(BaseModel):
    duration_ms: int
    subagents: int
    tokens: int

class ResultCardBlock(BaseModel):
    kind: Literal["result_card"] = "result_card"
    run_id: str
    title: str
    tldr: str
    findings: list[Finding]
    recommend: Optional[Recommend] = None
    links: list[Link] = Field(default_factory=list)
    feedback: FeedbackBlock
    stats: RunStats

AgentBlock = TextBlock | StatusLineBlock | QuestionCardBlock | ResultCardBlock

class AgentMessage(BaseModel):
    blocks: list[AgentBlock]
```

### 5.2 SSE event 扩展

现有 thread stream `/threads/{thread_id}/runs/stream` 增加一种事件：

```jsonc
{ "type": "block", "message_id": "...", "block": <AgentBlock JSON> }
```

旧的 `assistant_message` event **删除**（dev 阶段无用户、无兼容包袱）。

### 5.3 LLM structured output 调用

lead_agent 在产出每条 agent message 时：

```python
structured_llm = llm.with_structured_output(AgentMessage)
result: AgentMessage = await structured_llm.ainvoke(prompt_with_context)
for block in result.blocks:
    await emit_block_event(thread_id, message_id, block)
```

**关键约束**（写入 system prompt）：
- 不输出任何不在 4 类 block schema 内的字段
- 同 thread 同时最多 1 个未回答的 `question_card`
- 每个 run 必须以 `result_card` 结尾
- `phase` 切换时**必须**先发 `status_line`

### 5.4 Result_card 的"汇总卡顿"处理（P0-1）

`with_structured_output` 是一次性返回完整 JSON，从最后一个 `status_line` 到 `result_card` 出现之间会有 10–30s 静默。

**对策（本期实施）**：
- agent 在调用 result_card structured output **之前**，必先发一条
  ```
  status_line { tone: "info", label: "正在汇总结果（约 10-20s）" }
  ```
- 这条 status_line 在 prompt 里被强制约束作为 "result_card 前置步骤"
- 前端在该 status_line 出现后显示一个轻量进度指示

**升级路径（不在本期）**：用 `partial_json_parser` 做 result_card 的渐进字段解析，让 TL;DR → findings → recommend 流式出现。先按上述简化方案，预期不够再升级。

### 5.5 LLM JSON 解析失败的降级（X-1，强制保留）

即使用 `with_structured_output`，LLM 偶尔产出无效 JSON。这是模型不确定性，不是兼容问题。

**对策**：
- backend 解析失败时**降级**为 `TextBlock { content: "<原始文本>" }` 推送给前端
- 同时上报 metric 与日志（不向用户报错）
- 失败率 > 1%（建议阈值，可在 ops 配置里调）时自动告警

**这条不是 fallback for compat，是 fallback for LLM 不确定性，必须保留**。

---

## 6. 横切机制

### 6.1 暂停 / 中断（A3）

**Backend**：
- `ParallelExecutor` 加 `pause_event: asyncio.Event`，在每个 phase 边界 + `asyncio.gather` 之前 check：
  ```python
  if self._pause_event.is_set():
      await self._wait_until_resumed()
  ```
- 新 endpoint：
  - `POST /workspaces/{id}/runs/{run_id}/pause` → set event
  - `POST /workspaces/{id}/runs/{run_id}/resume` → clear event
  - `POST /workspaces/{id}/runs/{run_id}/cancel` → 取消整个 run（用于 chat 中断按钮）

**LangGraph 限制**：`create_react_agent` 内部的 tool call 不能 mid-call 立刻暂停。**承认这一点**：暂停 = 等当前 subagent 完成后停在 phase 边界。前端按钮文案对应为「在下个安全点暂停」，不误导用户。

**前端**：
- 右面板 Header 暂停按钮（A3 上半部分）
- chat InputArea 中断按钮（A3 下半部分，调 `cancel`）+ 用户在 chat 里直接打字（如"等等先别读那篇"）由 lead_agent 识别成中断指令

### 6.2 持久化（B3）

**新表 `workspace_run`**（Alembic 迁移）：

```sql
CREATE TABLE workspace_run (
    id              UUID PRIMARY KEY,
    workspace_id    UUID NOT NULL REFERENCES workspace(id),
    thread_id       UUID NOT NULL REFERENCES thread(id),
    title           TEXT NOT NULL,
    started_at      TIMESTAMPTZ NOT NULL,
    completed_at    TIMESTAMPTZ,
    status          TEXT NOT NULL,          -- running/paused/completed/cancelled/failed
    result_card     JSONB,                   -- 完成后填入
    stats           JSONB,                   -- duration_ms, subagents, tokens
    created_at      TIMESTAMPTZ DEFAULT now(),
    deleted_at      TIMESTAMPTZ              -- soft delete
);

CREATE INDEX ON workspace_run (thread_id, started_at);
```

`subagent_task` 表保留，加外键 `run_id` 关联。

**全持久化策略**：每一轮 run 的完整 phase + subagent 树 + result_card payload 都落库。用户在 result_card 上有「删除这一轮」操作（只删 run record，不删跨 run 复用的文献库 / artifact）。

### 6.3 错误处理（C3，按严重度自动分流）

**严重度判定**：在 `ParallelExecutor._execute_task` 中，subagent spawn 时传入 `metadata.criticality: "low" | "high"`（默认 low）。

- **low**（单 subagent 失败、可跳过、对最终结果影响有限）→
  - subagent.status = "failed"
  - lead_agent 在 chat 插一条 `status_line { tone: "warn", label: "phase N 有 1 个 subagent 失败，已跳过" }`
  - 主流程不停
- **high**（关键路径失败、phase 整体阻塞、影响 result 完整性）→
  - 自动 pause run（复用 §6.1 机制）
  - lead_agent 弹 `question_card { question: "...", pills: [...] }`，列出选项："跳过该步" / "重试" / "提供替代输入"

判定规则由 lead_agent 在 spawn subagent 时显式标注，不依赖 LLM 启发判断。

---

## 7. URL 参数承接（P1-1）

`/workspaces/[id]/chat` 接收的 URL 参数继续由 `parseWorkspaceThreadEntrySeed()` 解析为 `entrySeed`，但传给后端 thread 创建/恢复调用，由 lead_agent 处理而非前端 inject 消息。

| URL 参数组合 | ChatThread 行为 | lead_agent 行为 |
|---|---|---|
| `entry=open` + `feature=X` | 自动发送种子 prompt | 直接 `text` block 开场 + 启动第一个 phase |
| `entry=resume` | 不自动发送，渲染 RunList 历史，焦点在输入框 | 不开新 run |
| `onboarding=true` | 自动发送 `__onboarding__` | 用固定欢迎 `text` block 回复，等用户输入 |
| `source_artifact_id=X` | 把 artifact id 存入 `entrySeed.params.sourceArtifactId`，不在 chat 渲染为用户消息 | 通过 system context 拿到 artifact 内容，第一段 `text` 引用它，不复述全文 |
| `paper_title` + `paper_abstract` | 注入 entrySeed.params | 第一个 phase 直接用这些参数启动检索 |

**约束**：URL 解析逻辑保持单一来源（`lib/workspace-thread-entry.ts`），不在多个组件里重复实现。

---

## 8. Backend prompt 改造

### 8.1 删除项

**lead_agent** ([backend/src/agents/lead_agent/agent.py](../../backend/src/agents/lead_agent/agent.py)) 与 **skill prompts** ([backend/src/workspace_features/skills.py](../../backend/src/workspace_features/skills.py)) 中：

- 内部 taxonomy 词：`message_feature_proposal`、`意图置信度 N%`、turn 编号、graph 节点名
- 自我汇报短语：`"我会先复用..."`、`"将进入...执行链路"`、`"识别依据：..."`
- 旧的 `NextStepsBlock` / `MissingInputBlock` 等模板字符串

### 8.2 注入项

- 4 类 block 输出格式约束（schema 描述 + 范例）
- 5 条操作原则（§2 的 prompt 化版本）
- 行为规则：
  - "在真实岔路才用 question_card"
  - "每条 thread 同时最多 1 个未回答的 question_card"
  - "phase 切换前必须发 status_line"
  - "result_card 前必须发一条 '正在汇总结果' 的 status_line"

### 8.3 i18n（P1-3）

所有 block 内字符串走 i18n key（`blocks.<kind>.<key>`），不硬编码中文。新增 locale key 表作为契约，挂在 [frontend/locales/cn.json](../../frontend/locales/cn.json) 和 `en.json`（即使 en 暂时和 cn 一致也单独维护）。

---

## 9. 边界声明（OUT OF SCOPE）

- **Mobile 适配**：本期不做。`<lg` 断点显示"请在桌面端使用"占位，不做单列堆叠
- **多 thread 并行 run**：一个 thread 同时只能有一个 active run。用户在 thread A 跑着的时候打开 thread B，B 的状态独立
- **暗色模式**：跟随当前 workspace 主题，不单独设计
- **Result_card 字段流式渲染**：本期用 §5.4 简化方案，不做 `partial_json_parser`

---

## 10. 测试策略

| 层 | 工具 | 覆盖 |
|---|---|---|
| Frontend 组件 | vitest + Testing Library | `LiveWorkflowPanel` 用 mock `subagent.updated` fixture（done / running / waiting / failed）渲染对照；`ChatThread` 渲染 4 类 block 的快照；空态、Run 折叠、自动滚动 |
| Frontend 集成 | Playwright | 完整跑：用户输入 → 看到 status_line → 收到 question_card → 回答 → 看到 result_card → 点反馈 pill → 旧 run 折叠 + 新 run 出现 |
| Backend block 输出 | pytest | 对每个 skill prompt 跑 ≥3 个用户输入，断言：① 不出现 jargon 黑名单词 ② 输出符合 `AgentMessage` schema ③ question_card 在多轮交互中 ≤1 个未回答 ④ result_card 前必有 "正在汇总" status_line |
| 错误处理 | pytest | 模拟 subagent 失败：`criticality=low` → status_line warn；`criticality=high` → pause + question_card 阻塞 |
| LLM JSON 失败降级 | pytest | mock LLM 返回 invalid JSON → 断言降级为 TextBlock 且 metric 上报 |
| 暂停机制 | pytest | 调用 pause endpoint → ParallelExecutor 在下个 phase 边界停止；resume 后从下个 pending phase 启动 |
| Prompt 防回归 | snapshot | 每个 skill 的 system prompt 做 snapshot test。改 prompt 的 PR 必须 reviewer 显式 approve snapshot diff（`pytest --snapshot-update` 后人工 review） |

---

## 11. 实施 Phase 排期建议

> 详细 task 拆分由 writing-plans 阶段产出，这里只是粗排序。

- **Phase 0 · 准备**：grep `useExecutionStore` 所有消费者；列出待删 `thread-blocks/*` 文件清单；新建 `workspace_run` 表的 alembic 迁移
- **Phase 1 · 协议层**：定义 `AgentBlock` Pydantic schema + frontend TypeScript 镜像；定义 `block` SSE event；删除 `assistant_message` 旧 event 路径
- **Phase 2 · Backend 改造**：lead_agent prompt 重写 + structured output 接入 + JSON 失败降级 + i18n key 契约
- **Phase 3 · Backend pause/cancel hooks**：ParallelExecutor pause_event + 3 个 endpoint
- **Phase 4 · 前端组件**：`useWorkflowStore` + `LiveWorkflowPanel` + `ChatThread` + 空态 + Run 折叠
- **Phase 5 · WorkspaceAssets** 搬家：从 4-tab Inspector 抽出 ArtifactLibrary / LiteraturePanel / KnowledgePanel，挂到 LiveWorkflowPanel 折叠区
- **Phase 6 · 测试 & prompt snapshot**：组件 + 集成 + prompt + 失败降级 + pause
- **Phase 7 · 清理**：删 `WorkspaceInspector` 旧 4-tab 容器（其中 `ArtifactLibrary` / `LiteraturePanel` / `KnowledgePanel` 子组件已在 Phase 5 搬到 `WorkspaceAssets`，仅删容器与原 tab 路由），删 `ComputeStage`、`thread-blocks/*` 历史 block 文件、`useExecutionStore`、`assistant_message` 旧 SSE 路径
- **Phase 8 · 联调**：Playwright e2e + 真实 LLM 跑通联邦学习场景的端到端验收

---

## 12. 验收标准

- [ ] 输入「我想写一篇论文，联邦学习结合大模型方向」后：agent 不输出任何 jargon、不重复按钮、不自我汇报
- [ ] agent 在合适时机用 question_card 提一个聚焦问题
- [ ] 右面板看到 phase 1（检索）→ phase 2（并行阅读 12 篇）→ phase 3（提炼）的实时变化
- [ ] phase 切换时 chat 出现一条 status_line
- [ ] 完成后 chat 出现 result_card，包含 TL;DR + 关键发现 + 推荐 + 反馈区
- [ ] 用户点反馈 pill 触发新 run，上一轮整体折叠
- [ ] 暂停按钮可在下个 phase 边界停下，resume 可继续
- [ ] 单 subagent 失败 → status_line warn；关键路径失败 → 阻塞 question_card
- [ ] LLM 返回 invalid JSON → 降级 TextBlock，前端无报错
- [ ] 用户上滑后 auto-follow 暂停，浮按钮"回到当前进度"出现
- [ ] WorkspaceAssets（成果/文献/上下文）在没有 active run 时默认展开

---

## 13. 已确认的设计决策（用于后续 plan / review 追溯）

- **Q1**：4 痛点全部需要重新设计
- **Q2**：agent 风格 = 直接动手 + 透明过程（A），加 brainstorming-style 提问
- **Q3**：右面板 = 实时工作流（A），匹配 langgraph subagent 真实拓扑
- **Q4**：右面板细节 6 + 1 决策全部保留（折叠已完成 / live preview / waiting → chat / 自动滚 / token 角标 / 2 列网格 / 多 subagent 时二级折叠）
- **Q5**：chat 3 决策全部保留（无自我汇报 / phase 切换插轻状态行 / question_card + pill）+ 在 chat 里出现 status_line
- **Q6**：result_card 4 决策全部保留（TL;DR 优先 / 编号 findings / recommend block / 反馈 pills + 自由输入）；多 run = C（已完成 run 整体折叠）
- **Q7**：暂停 = A3（按钮 + chat 中断都做）；持久化 = B3（全持久化、用户自删）；错误 = C3（按严重度自动分流）
- **Q8**：实施路径 B（前端重做 + 结构化 block 协议 + prompt 改造），彻底重构无 fallback
