# Workspace Prism Surface Design

Date: 2026-05-19

## Overview

Wenjin 当前对 `workspace` 和 `WenjinPrism` 的产品定义，其实已经隐含了一个很清楚的结构：

- `workspace / compute` 是科研工作流引擎
- `WenjinPrism` 是主稿编辑、编译、审阅、落稿的稿件基础设施

问题不在于理念不清楚，而在于实现层把 Prism 同时做成了三种东西：

1. workspace 的隐式桥接子资源
2. compute projection 里的 sidecar 状态
3. 一个通过 `/latex/:projectId` 外跳打开的独立编辑器

这三种身份同时存在，导致用户心智和系统边界都变得模糊。

本设计的目标，是把 Prism 收敛成一个清晰、稳定、可扩展的对象：

**Prism 不是 room，不是外挂系统，而是 workspace 的 manuscript surface。**

canonical 体验应当是：

- `workspace` 有两个主 surface：
  - `workbench surface`
  - `prism surface`
- `workbench` 管 chat / compute / rooms
- `prism` 管主稿编辑 / 编译 / PDF / review gate / apply-revert
- 两者共享同一个 workspace identity 和同一条结果闭环

## Problem Statement

### Current failure mode

当前实现里，workspace 与 Prism 的关系分散在四个不同层次：

1. **绑定关系是隐式的**
   - workspace 到 LaTeX 项目的主绑定并不是显式 schema 字段
   - 现状依赖 `latex_projects.llm_config.workspace_id`

2. **路由边界是割裂的**
   - workspace 主界面是 `/workspaces/:id`
   - Prism 入口是 `/latex/:projectId`
   - 用户会感到自己“跳到了另一个系统”

3. **Compute 对 Prism 的感知不是权威投影**
   - projection 会从 `execution.runtime_state` / `task.result` / `task.runtime_state` 里递归扫描 `latex_project_id`
   - 然后再回查 `LatexProject` 补状态

4. **前端 action contract 混合了三类语义**
   - room actions
   - execution / feature actions
   - prism actions
   - 但现在都塞在同一组 next actions 里，缺乏明确分层

### Why this feels messy

这会同时带来三种混乱：

1. **产品混乱**
   - 用户不知道 Prism 是 workspace 的一部分，还是另一个应用

2. **数据混乱**
   - workspace 与稿件的主绑定关系没有一等事实源

3. **实现混乱**
   - Prism 状态在 bridge metadata、task payload、compute projection、standalone latex routes 间来回穿梭

## Goals

- G1. 明确 `workspace -> prism` 的正式关系，去掉“半桥接半外挂”的状态
- G2. 让 Prism 成为 workspace 的 canonical manuscript surface
- G3. 让 compute / result card / next actions 都围绕同一个权威 Prism 绑定工作
- G4. 保留现有 `LatexEditorShell`、compile、PDF、file change review 能力，不推倒重来
- G5. 允许历史 `/latex/:projectId` 链接继续可用，但降级为兼容入口
- G6. 给后续 claim-evidence、review finding、citation binding 回写 Prism 留出稳定架构位置

## Non-Goals

- N1. 本轮不重写 Latex editor 内核
- N2. 本轮不把 Prism 做成一个 room drawer
- N3. 本轮不处理多稿件协作或多主稿并行编辑
- N4. 本轮不废弃所有 standalone LaTeX project 能力；仅收敛 workspace-owned manuscript 的 canonical path
- N5. 本轮不引入新的富文本或 block-based manuscript editor

## Alternatives Considered

### Option A: Keep current model, only rename and document it

优点：

- 改动最小

缺点：

- 用户心智仍然分裂
- 数据绑定仍然是隐式 JSON
- compute projection 仍然依赖 payload 扫描

结论：

- 不推荐

### Option B: Make Prism a workspace room

优点：

- 从 topbar 上看最统一

缺点：

- Prism 不是“上下文抽屉”，而是完整工作面
- 编译、PDF、file tree、diff preview 放进 room 会天然局促
- 会把主稿台降格成附属工具面板

结论：

- 不推荐

### Option C: Workspace-Scoped Prism Surface

做法：

- Prism 作为 workspace 的第二主界面存在
- canonical route 为 `/workspaces/:id/prism`
- `/latex/:projectId` 仅作为兼容入口或通用 LaTeX route

优点：

- 用户心智清晰
- 不牺牲 Prism 的全屏工作面属性
- 能把数据、路由、projection、actions 一次收拢

结论：

- **推荐方案**

## Chosen Design

### Product model

一个 workspace 有两个主 surface：

1. **Workbench Surface**
   - 路由：`/workspaces/:id`
   - 承载：
     - chat
     - compute
     - library / documents / tasks / runs / settings rooms

2. **Prism Surface**
   - 路由：`/workspaces/:id/prism`
   - 承载：
     - `LatexEditorShell`
     - file tree
     - compile / PDF
     - pending file changes
     - apply / discard / revert
     - Prism feedback and review workflows

这两个 surface 属于同一个 workspace，而不是两个平行产品。

### Canonical mental model

```text
Workspace
├── Workbench surface (workflow + context + results)
└── Prism surface (manuscript + compile + review)
```

用户感知应当是：

- 我在同一个 workspace 里切换不同工作面
- 不是从 workspace “跳到” Prism

## Domain Model

### Current state

当前主绑定依赖：

- `latex_projects.llm_config.workspace_id`
- `latex_projects.llm_config.bridge = "workspace_latex_project"`

这只能作为 bridge metadata，不适合作为一等关系。

### New canonical relationship

推荐在 `latex_projects` 上补齐显式字段：

```text
latex_projects
- id
- user_id
- workspace_id nullable
- surface_role nullable
```

字段语义：

- `workspace_id`
  - 表示该稿件属于哪个 workspace
  - `null` 表示 standalone LaTeX project

- `surface_role`
  - 首版只使用 `primary_manuscript`
  - 后续可扩展：
    - `primary_manuscript`
    - `supplementary_material`
    - `appendix_project`
    - `submission_package`

### Why this is better

- 绑定关系成为显式 schema 事实
- 查询不再依赖 JSON 路径
- compute / routes / permissions / analytics 都能直接围绕主绑定工作
- bridge metadata 可以退回到“运行态控制信息”角色

### Bridge metadata after migration

`llm_config.metadata` 继续保留，但职责收缩为：

- `managed_files`
- `file_changes`
- `applied_file_changes`
- `keywords`
- generated section map / auxiliary writeback metadata

它不再承载“这个 project 属于哪个 workspace”这一主事实。

## Routing Model

### Canonical routes

- `GET /workspaces/:id`
  - workspace workbench surface

- `GET /workspaces/:id/prism`
  - workspace Prism surface

### Removed standalone routes

- `GET /latex/:projectId` has been removed.
- Workspace-owned Prism is the only manuscript collaboration surface.
- Historical standalone LaTeX links fail closed instead of redirecting through a compatibility layer.

### Frontend navigation semantics

`open_prism` / `preview_prism_changes` now resolve to `/workspaces/:id/prism`.

结果是：

- 在 workspace 内触发 Prism action 时，用户留在 workspace 语义中
- 不再存在裸 project route 作为运行时入口

## Backend Architecture

### New service: `WorkspacePrismService`

新增一个产品级服务层，职责与 `WorkspaceLatexProjectService` 分离：

#### `WorkspacePrismService`

职责：

1. 查询 workspace 的 primary manuscript
2. ensure primary manuscript 存在
3. 构建 workspace-owned Prism projection
4. 解析 route handoff
5. 暴露 canonical Prism action metadata

建议接口：

```python
class WorkspacePrismService:
    async def get_primary_project(self, workspace_id: str, *, user_id: str) -> LatexProject | None: ...
    async def ensure_primary_project(self, workspace_id: str, *, user_id: str) -> LatexProject: ...
    async def get_surface_projection(self, workspace_id: str, *, user_id: str) -> dict[str, Any]: ...
    async def resolve_workspace_from_project(self, project_id: str, *, user_id: str) -> tuple[str | None, LatexProject | None]: ...
```

#### `WorkspaceLatexProjectService`

保留为底层 bridge writer，职责收缩为：

- 初始化模板文件
- 同步 outline / references / generated sections
- 生成 pending file changes
- 维护 managed_files metadata

也就是说：

- `WorkspacePrismService` 定义“它是谁”
- `WorkspaceLatexProjectService` 负责“往里面写什么”

### Router changes

#### Workspace router

保留并升级：

- `POST /workspaces/{id}/prism/ensure`

新增：

- `GET /workspaces/{id}/prism`
  - 返回 workspace Prism surface shell metadata

可选新增：

- `GET /workspaces/{id}/prism/projection`
  - 若希望与 editor shell 解耦，可给 Prism surface 一个独立 projection

#### LaTeX router

保留：

- `/latex/projects/...`
- `/latex/:projectId`

但对 `GET /latex/:projectId` 增加 workspace-owned 解析逻辑。

## Compute Projection Changes

### Current state

当前 Prism projection 的来源是：

1. 递归扫描 execution runtime payload
2. 递归扫描 task result / task runtime_state
3. 找到 `latex_project_id` 后拼 projection
4. 再用 `LatexPrismStatusResolver` 回查最新状态

这会让 Prism projection 更像“任务产出的副产品”。

### New rule

对于 workspace-owned primary manuscript：

- Prism 是 workspace authoritative surface
- execution 只需要持有 pointer
- compute projection 直接读取 authoritative Prism state

### Revised compute contract

`ComputeProjection.prism` 的语义改为：

- 表示“当前 execution 关联的 workspace primary manuscript 状态”
- 不是“在各种 payload 里扫到的第一个 latex_project_id”

### Implementation direction

1. execution / task 层保留 `latex_project_id` pointer
2. `ComputeProjectionService` 先判断当前 execution 是否关联 workspace-owned Prism
3. 若是，则直接通过 `WorkspacePrismService` / `LatexPrismStatusResolver` 构造 projection
4. projection 只读 workspace-owned Prism surface，不再扫描 execution payload

### Expected result

Prism 在 Compute 中从：

- `task sidecar metadata`

升级为：

- `workspace-owned manuscript state`

## Frontend Architecture

### Workspace shell

workspace shell 不需要把 Prism 塞进 rooms topbar。

推荐结构：

```text
Workspace shell
├── Surface switch
│   ├── Workbench
│   └── Prism
└── Active surface content
```

### Surface switch behavior

- 在 `/workspaces/:id` 打开 `Workbench`
- 在 `/workspaces/:id/prism` 打开 `Prism`
- 用户切换时保留同一个 workspace identity

### Why not a room

room 是：

- library
- documents
- tasks
- settings

这些都是上下文或附属操作面。

Prism 则是：

- 重编辑
- 重预览
- 重编译
- 重审阅

它应该是 surface，不应该被降级成 drawer。

### Reuse strategy

不重写 `LatexEditorShell`。首版直接在 workspace Prism route 下复用：

- `LatexEditorShell`
- compile APIs
- file change preview/apply/discard/revert APIs
- feedback APIs

变化主要在：

- 外层 route container
- workspace-aware navigation
- workspace context breadcrumb / return affordance

## Action Contract Changes

### Current problem

当前 `SUPPORTED_BLOCK_ACTIONS` 把这几类动作混在一起：

- room navigation
- feature relaunch / resume
- Prism navigation

这导致 UI 上虽然都表现成按钮，但语义不清晰。

### New action taxonomy

next actions 应收敛成三类：

1. `workspace_room_action`
   - `open_artifact`
   - `import_references`
   - future room-focused actions

2. `execution_action`
   - `resume_execution`
   - `rerun_feature`
   - `trigger_feature`
   - `continue_thread`

3. `prism_action`
   - `open_prism`
   - `preview_prism_changes`
   - future `open_compile_pdf`
   - future `focus_prism_file_change`

### Immediate implementation rule

即使首版还不改单个 action schema，也至少应让前端 presentation 层显式区分：

- room-handoff
- execution-handoff
- prism-handoff

这样 `CompletedView`、`ResultCard`、Compute Stage 才能用不同的交互样式承载不同动作。

## UX Flows

### Flow 1: Open manuscript from workspace

1. 用户进入 workspace
2. 点击 surface switch 的 `Prism`
3. 进入 `/workspaces/:id/prism`
4. 打开 linked primary manuscript

### Flow 2: Capability writes pending changes

1. capability 完成
2. compute / completed view 显示 Prism pending review
3. 用户点 `预览待确认修改`
4. 进入 `/workspaces/:id/prism`
5. editor 自动聚焦 pending file changes review 区

### Flow 3: Return from manuscript to workbench

1. 用户在 Prism 完成 apply / revert / compile
2. 点击 `返回工作台`
3. 回到 `/workspaces/:id`
4. Compute projection 里看到更新后的 Prism status

### Flow 4: Removed direct link

1. 用户访问 `/latex/:projectId`
2. 系统不再提供 standalone Prism runtime route
3. 用户从 workspace surface switch 或 Prism action 进入 `/workspaces/:id/prism`

## Migration Plan

### Phase 1: Data model

1. 为 `latex_projects` 添加：
   - `workspace_id`
   - `surface_role`
2. 回填：
   - 从 `llm_config.workspace_id` 迁移到显式字段
3. 对 workspace-owned primary manuscript 建索引：
   - `(workspace_id, surface_role)`

### Phase 2: Service split

1. 新增 `WorkspacePrismService`
2. `WorkspaceLatexProjectService` 退回桥接写入层
3. `ensure_workspace_prism_project` 改走 `WorkspacePrismService`

### Phase 3: Routing

1. 新增 `/workspaces/:id/prism`
2. 移除 `/latex/:projectId` standalone runtime route
3. 前端所有 `open_prism` / `preview_prism_changes` handoff 改指向 workspace Prism route

### Phase 4: Compute

1. `ComputeProjectionService` 引入 authoritative Prism source
2. 移除 execution payload scan 作为 Prism 状态来源
3. `LatexPrismStatusResolver` 继续负责 file change / compile 状态刷新

### Phase 5: Frontend shell

1. workspace shell 增 `Workbench / Prism` surface switch
2. Prism route 复用 `LatexEditorShell`
3. 给 Prism 增 workspace-aware back navigation / header context

### Phase 6: Cleanup

1. 清理对 `prism_url` 的随意拼接依赖
2. 清理对 `llm_config.workspace_id` 查询的主路径依赖
3. 清理 compute 中不再需要的 Prism payload 猜测逻辑

## Testing Strategy

### Backend

- migration test：旧 `llm_config.workspace_id` 正确回填
- service test：workspace 只能拿到自己的 primary manuscript
- route test：
  - `/workspaces/:id/prism` 返回 linked surface
  - `/latex/:projectId` 不再作为运行时入口
- compute projection test：
  - authoritative Prism state 优先
  - execution payload 不参与 Prism projection

### Frontend

- route test：
  - `/workspaces/:id/prism` 渲染 `LatexEditorShell`
- action handoff test：
  - `open_prism` / `preview_prism_changes` 打开 workspace Prism route
- surface switch test：
  - workbench/prism 切换不丢 workspace context

### E2E

- capability 生成 pending file change
- 从 completed execution 点 `预览待确认修改`
- 进入 Prism surface
- apply / revert 后回到 workbench
- compute panel 状态正确刷新

## Risks and Mitigations

### Risk 1: Legacy links break

缓解：

- 保留 `/latex/:projectId`
- workspace-owned project 走 redirect

### Risk 2: Workspace shell becomes too heavy

缓解：

- Prism 作为独立 route，不与 workbench 同页渲染
- 只共享 workspace identity 和 navigation shell

### Risk 3: Migration leaves dual source of truth

缓解：

- 显式规定 `workspace_id` / `surface_role` 为 canonical binding
- `workspace_id` / `surface_role` 是 canonical binding；`llm_config.workspace_id` 不作为运行时绑定来源

### Risk 4: Compute projection regression

缓解：

- 通过 authoritative Prism surface projection 构建 Compute projection
- 用 targeted compute tests 锁定行为

## Final Recommendation

WenjinPrism 最合适的归位方式，不是成为一个 room，也不是继续维持外挂入口，而是：

**作为 workspace 的 manuscript surface 存在。**

其核心收敛原则是：

1. **关系显式化**
   - workspace 与 primary manuscript 绑定成为 schema-level fact

2. **路由归属化**
   - canonical Prism route 属于 workspace，而不是裸 project

3. **投影权威化**
   - compute / next actions / result consumption 都围绕 workspace-owned Prism state

4. **体验双主面化**
   - workbench 与 prism 是同一 workspace 下的两个主工作面

这会让 Wenjin 的整体结构变得更像一个稳定产品，而不是“工作台 + 一个强耦合外挂编辑器”的拼接体。
