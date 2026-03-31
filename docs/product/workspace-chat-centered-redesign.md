# Workspace Chat-Centered Redesign

更新时间: 2026-03-23
状态: Proposal
适用项目: `wenjin`

## 1. 背景

当前 Wenjin 已具备以下基础能力:

- `workspace` 作为任务容器
- `feature` 作为可执行模块
- `chat thread` 作为会话容器
- `artifact` / `paper` / `task` 作为过程与结果记录

但当前产品入口仍偏“模块卡片首页”，没有充分发挥 chat 作为任务驾驶舱的作用，主要问题:

1. 用户对 `workspace`、`thread`、`feature` 的关系感知不清晰。
2. Thesis workspace 缺少嵌入式 chat 主入口，交互割裂。
3. chat 可以发送消息，也有快捷动作，但尚未成为统一任务编排中心。
4. 长短期记忆缺少清晰的产品语义分层。
5. 历史仓库中仍有不少高价值能力尚未迁入统一 feature pipeline。

本方案目标不是“把模块做没”，而是把模块收编到 chat-centered workspace 中。

当前实现补充说明:

- feature 卡片、artifact follow-up、activity retry 已统一落到 `chat/new`
- 入口 query 会携带 `feature + skill + seed params`
- 首次发送会把 `metadata.orchestration` 一并发给后端，优先命中 canonical feature bridge

## 2. 产品定位

### 2.1 核心定义

- `Workspace = 一个完整任务`
- `Chat = 任务驾驶舱`
- `Feature / Module = 结构化执行器`
- `Artifact = 任务产物`
- `Thread = 任务内会话主线 / 分支`
- `Memory = 用户偏好 + 任务稳定事实 + 当前会话上下文`

### 2.2 典型任务

- 写一篇 LLM 方向的 SCI 论文
- 完成一个 agent 系统的软件著作权申请
- 完成一个专利申请草案
- 完成一个课题申报书
- 完成一个学位论文从开题到导出的全链路

### 2.3 设计原则

1. `workspace` 必须表达任务，不表达单次对话。
2. `chat` 必须表达“下一步该做什么”，不是单纯问答框。
3. `module` 必须可从 chat 启动，也可独立进入深度编辑。
4. `artifact` 必须成为所有模块的统一结果落点。
5. `thread` 默认弱感知，但不能被删掉。

### 2.4 范围边界 / Non-Goals

本方案首要解决的是“入口和编排”，不是一次性重写整个平台。

首期明确不做:

1. 不把 `workspace` 退化为 `session`。
2. 不推翻现有 `FeatureExecutionHandler + TaskService + registry` 主链路。
3. 不在 Phase 1 就重做复杂的 thread schema 或 branch diff 可视化。
4. 不要求首期把旧项目全部能力一次性迁回。
5. 不把 module 深度页做成 chat 的附属弹窗，复杂工作页仍保持独立。

## 3. 信息架构

### 3.1 实体关系

```text
User
  ├─ Global Memory
  ├─ Workspace A: "LLM SCI论文"
  │    ├─ Main Thread
  │    ├─ Branch Thread(s)
  │    ├─ Features
  │    ├─ Artifacts
  │    ├─ Papers / Literature
  │    └─ Tasks / Runtime
  └─ Workspace B: "Agent软著"
       ├─ Main Thread
       ├─ Branch Thread(s)
       ├─ Features
       ├─ Artifacts
       └─ Tasks / Runtime
```

### 3.2 用户可见层级

用户默认只感知三层:

1. 工作区列表
2. 某个 workspace 的任务驾驶舱
3. 某个模块的深度工作页

`thread` 默认不作为一级导航项，只在 chat 内体现:

- 主会话
- 历史会话
- 分支会话

## 4. 首页改版

## 4.1 目标

把当前“模块卡片首页”升级为“任务驾驶舱首页”。

### 4.2 建议布局

```text
┌──────────────────────────────────────────────────────────────┐
│ Header: Workspace Name / Type / Discipline / Progress       │
├──────────────────────────────────────────────────────────────┤
│ Task Summary Strip                                          │
│ 当前阶段 | 下一步建议 | 最近活动 | 风险提醒                 │
├───────────────┬──────────────────────────────┬──────────────┤
│ Left Rail     │ Main Chat                     │ Right Rail   │
│               │                               │              │
│ 阶段轨道      │ 主会话                        │ 产物库       │
│ 模块状态      │ Assistant建议                 │ 文献         │
│ 快速入口      │ 任务卡 / 运行态 / 追问        │ 运行面板     │
│               │                               │ 最近活动     │
├───────────────┴──────────────────────────────┴──────────────┤
│ Recommended Modules / More Tools                            │
└──────────────────────────────────────────────────────────────┘
```

### 4.3 首屏模块

- Header
- Task Summary Strip
- Main Chat
- Recommended Modules
- Artifact Snapshot
- Literature Snapshot

### 4.4 当前代码对应关系

可复用现有组件:

- `ChatPanel.tsx`
- `KnowledgePanel.tsx`
- `LiteraturePanel.tsx`
- `TaskRuntimePanel.tsx`
- `ModuleCard.tsx`
- `RecentArtifacts.tsx`

需调整的位置:

- `frontend/app/(workbench)/workspaces/[id]/page.tsx`
- `frontend/app/(workbench)/workspaces/[id]/layout.tsx`

## 5. Chat 作为任务驾驶舱

### 5.1 chat 的新职责

chat 不只承担“对话”，还承担:

1. 解释当前任务状态
2. 推荐下一步动作
3. 补齐模块所需参数
4. 启动 feature 执行
5. 展示任务运行态和结果摘要
6. 引导用户进入深度编辑页

### 5.2 chat 中允许出现的内容块

- 普通问答消息
- Assistant 任务建议卡
- Feature 启动确认卡
- Task Runtime 卡
- Artifact 结果卡
- Review / Warning 卡
- Next Step 建议卡

### 5.3 推荐交互

用户输入:

- “帮我先做文献综述”
- “根据现有内容生成论文大纲”
- “把这个软著的技术说明先起草出来”
- “对当前论文做一次 AI 评审”

assistant 行为:

1. 识别目标 feature
2. 检查缺失参数
3. 缺参时只问最少问题
4. 参数齐全后通过统一 feature pipeline 启动任务
5. 在 chat 内流式展示运行状态
6. 完成后把结果挂到 artifact，并引导下一步

### 5.4 与现有实现的关系

当前前端已支持:

- chat 发送消息
- thread 恢复与切换
- 通过 `executeWorkspaceFeature(..., threadId)` 触发 feature

当前缺的是:

- assistant 自动调度 feature，而不是仅依赖快捷按钮
- feature 结果在 chat 中结构化回显
- 对话驱动的补参流程

## 6. Thread 设计

### 6.1 产品语义

不建议让用户理解为“workspace = session”。

建议改为:

- 每个 workspace 默认存在一个 `Main Thread`
- 用户可以显式新建 `Branch Thread`
- 分支用于探索不同方向，不直接污染主线

### 6.2 用户体验策略

默认隐藏复杂度:

- 首次进入 workspace 自动恢复 `Main Thread` 或最近活跃 thread
- “新会话”文案建议改成“新分支”
- “历史会话”文案建议改成“主线 / 分支记录”

### 6.3 数据层建议

现有 `chat_threads` 表已可满足基本需求，但建议后续增加:

- `kind`: `main | branch`
- `parent_thread_id`: 允许分支挂主线
- `pinned_artifact_id`: thread 当前关注的产物
- `context_scope`: `workspace | feature | artifact`

这些字段不是首期必需，但对长期产品演化有价值。

## 7. 记忆模型

### 7.1 建议采用三层记忆

#### A. Thread Memory

作用:

- 当前会话短期上下文
- 上下几轮追问
- 当前未完成的局部任务

边界:

- 仅服务当前 thread

#### B. Workspace Memory

作用:

- 当前任务稳定事实
- 已确认的研究主题
- 已确认的大纲与约束
- 当前任务阶段
- 已采纳的评审意见

边界:

- 同一 workspace 内共享
- 分支可读，写入需要筛选

#### C. User Memory

作用:

- 用户跨任务偏好
- 引用格式偏好
- 语言偏好
- 写作风格偏好

边界:

- 跨 workspace 生效

### 7.2 当前实现与目标差距

当前 `UserKnowledge` 已支持 `workspace_context`，适合作为 User Memory + Workspace Memory 的基础表。

建议增加一层更明确的产品语义:

- `workspace_facts` 或 `workspace_memory_blocks`

原因:

- workspace 事实不应完全依赖聊天抽取
- 模块产出中的关键结论应直接结构化写入

### 7.3 首期建议

首期不新增复杂 memory 子系统，先做:

1. 修复 chat -> long-term memory 的闭环
2. 明确区分:
   - thread history
   - workspace facts
   - user preferences
3. feature 成功后继续抽取稳定事实
4. chat 成功后只抽取高置信偏好与上下文，不抽大量噪音

## 8. 模块体系

### 8.1 模块分层

建议把 feature 分成两类:

#### Core Modules

直接对应任务主链路阶段:

- 深度调研
- 文献综述
- 大纲生成
- 正文写作
- 图表生成
- AI 评审
- 导出交付

#### Support Modules

横向增强能力:

- 期刊推荐
- 实验设计
- 可行性分析
- 现有技术对比
- 合规检查

### 8.2 首页显示策略

首页不应平铺所有 feature。

建议:

- 默认展示“推荐下一步模块”3-5 个
- 其余模块进入“全部工具”
- 推荐逻辑基于:
  - workspace 类型
  - 当前 artifact 状态
  - 最近成功任务
  - 用户最近一次 assistant 建议

## 9. 五类 workspace 的推荐任务链

### 9.1 Thesis

1. 深度调研
2. 文献管理 / 文献综述
3. 开题调研
4. 论文写作
5. 图表生成
6. AI 评审
7. 编译导出

### 9.2 SCI

1. 深度调研
2. 文献检索 / 文献综述
3. 论文分析
4. 论文写作
5. 图表生成
6. 同行评审
7. 期刊推荐
8. 导出

### 9.3 Proposal

1. 背景调研
2. 申报书大纲
3. 实验设计 / 可行性分析
4. 正文完善
5. AI 评审
6. 导出

### 9.4 Software Copyright

1. 材料准备
2. 技术说明
3. 系统亮点整理
4. 材料审校
5. 导出

### 9.5 Patent

1. 现有技术检索
2. 专利框架
3. 新颖性比较
4. 说明书完善
5. 导出

## 10. 关键页面交付说明

### 10.1 Workspace Dashboard

目标:

- 任务总览
- 任务驾驶舱
- 推荐下一步

首期交付:

- 统一五类 workspace 都带 chat panel
- 显示任务概览条
- 显示推荐下一步模块

### 10.2 Chat Panel

目标:

- 主入口
- 主线 / 分支管理
- feature 启动与状态回显

首期交付:

- “新会话”改“新分支”
- 历史区增加主线标识
- assistant 消息支持任务卡
- QuickActions 升级为 Recommended Actions

### 10.3 Module Deep Work Page

目标:

- 面向复杂参数和深度编辑

要求:

- 从 chat 可跳转进入
- 能看到来源 thread / 来源 task
- 能回到 chat 主线

### 10.4 Artifact Detail View

目标:

- 把结果当一等对象，而不是附属文本

要求:

- 展示来源 feature
- 展示创建时间 / 版本
- 展示可执行下一步动作

## 11. 后端改造清单

### 11.1 P0

1. 增加统一 tool: `run_workspace_feature`
   - 输入: `workspace_id`, `feature_id`, `params`, `thread_id`
   - 输出: `task_id`, `status`, `message`

2. 增加统一 tool: `list_workspace_features`
   - 输入: `workspace_id`
   - 输出: 当前可执行 feature 列表

3. 增加统一 tool: `list_workspace_artifacts`
   - 输入: `workspace_id`
   - 输出: 关键产物摘要

4. 修复 chat memory persistence 闭环

5. 为 assistant 响应增加“模块启动建议”结构

### 11.2 P1

1. 给 `chat_threads` 增加主线 / 分支语义字段
2. 增加 `workspace summary` 聚合接口
3. 增加推荐下一步接口
4. 为 artifact 增加“recommended_next_features”

### 11.3 P2

1. 增加 workspace facts 存储层
2. 增加跨模块引用关系
3. 增加 artifact-based context pinning

## 12. 前端改造清单

### 12.1 P0

1. 统一 workspace 首页布局
2. Thesis workspace 恢复 chat panel
3. 首页顶部增加 Task Summary Strip
4. `QuickActions` 改为推荐动作区
5. chat 中展示任务卡 / 结果卡
6. chat 历史文案改成主线 / 分支语义

### 12.2 P1

1. 首页支持“下一步推荐”
2. chat 中支持 feature 补参卡
3. artifact 详情页支持“继续此任务”
4. module page 增加“回到主线 chat”

### 12.3 P2

1. 引入 workspace timeline
2. 引入分支对比视图
3. 引入 artifact lineage 可视化

## 13. 迁移策略

### 13.1 原则

1. 不推翻现有 canonical feature pipeline
2. 不重新发明 task system
3. 不把旧项目能力直接按旧 API 原样搬回
4. 新交互全部围绕现有 registry / task / artifact 体系展开

### 13.2 旧能力回补策略

按“高频 + 高价值 + 易接入 pipeline”顺序:

1. 同行评审
2. 文献综述
3. 期刊推荐
4. 实验设计
5. AI 配图增强
6. 政策分析

### 13.3 首期范围边界

Phase 1 只做“任务驾驶舱成形”，不做“全自动规划器”。

首期用户体验边界建议明确为:

1. chat 成为 workspace 主入口，但模块页继续保留。
2. assistant 先支持“推荐动作 + 部分 feature 直接调度”，不是一开始覆盖所有 feature。
3. thread 首期先做主线 / 分支命名和默认恢复策略，不强依赖数据库 schema 变更。
4. memory 首期先修复闭环和降噪，不新增过重的记忆产品形态。

### 13.4 实施依赖图

建议按以下依赖顺序实施，避免前端先做出不可落地交互:

1. 先统一 workspace dashboard 和 thesis chat 入口。
2. 再补 `workspace summary` / `recommended next step` 等聚合数据。
3. 再给 lead agent 增加 `run_workspace_feature` 等 tool，完成 chat -> feature 编排。
4. 再补 chat 结构化消息卡片，承接任务状态和结果回显。
5. 最后再做 memory 分层增强和旧能力回补。

换句话说:

- 没有统一入口，chat-centered 只停留在概念层。
- 没有 agent tool，chat 无法真正成为任务编排中心。
- 没有结构化消息，task / artifact 无法在 chat 内稳定呈现。
- 没有 memory 闭环，workspace 长期任务体验会持续退化。

## 14. 路线图

### Phase 1: 入口重构

目标:

- chat-centered workspace 成形

交付:

- 统一 dashboard
- thesis 补回 chat
- 推荐动作区
- 主线 / 分支命名调整

### Phase 2: 编排重构

目标:

- assistant 真正能调度 feature

交付:

- `run_workspace_feature` tool
- 对话补参
- 任务卡和结果卡

### Phase 3: 记忆与推荐

目标:

- 让 assistant 真正“记住任务”

交付:

- chat memory 闭环
- workspace facts
- next-step recommendation

### Phase 4: 能力回补

目标:

- 把历史仓库的关键能力拉回统一平台

交付:

- 补齐高价值 feature
- 全部接入 canonical pipeline

## 15. 验收标准

### 产品层

1. 五类 workspace 首页都有 chat 主入口
2. 用户可在 chat 中直接发起关键任务
3. 用户能感知当前阶段与下一步建议
4. 模块结果自动沉淀为 artifact
5. 用户能在同一 workspace 内管理主线 / 分支

### 技术层

1. 所有 feature 仍走统一 `FeatureExecutionHandler + TaskService`
2. chat 发起的 feature 执行可绑定 `thread_id`
3. 任务状态与 workspace event stream 保持一致
4. chat 长期记忆落库闭环可用
5. 新交互不破坏现有 feature registry 契约

## 16. 推荐首批实施项

建议先做以下 6 项:

1. 统一 workspace 首页布局
2. Thesis workspace 恢复 chat panel
3. `QuickActions` 升级为推荐动作区
4. 增加 `run_workspace_feature` agent tool
5. 修复 chat memory persistence
6. 在 chat 中展示任务卡和结果卡

这 6 项改动最小、用户感知最强、且不需要推翻现有后端主链路。
