# Product UX Repair Convergence Spec

日期：2026-06-19  
状态：Proposed  
适用范围：Wenjin workspace 前台体验、Workbench 右侧工作台、资料库/候选结果、Prism 辅助体验、Admin SSOT 管理、移动端与可访问性。

## 1. 背景

本 spec 聚合 2026-06-19 浏览器产品审查发现的问题。审查证据保存在：

- `/Users/ze/wenjin/.tmp/product-audit-20260619-round2/round2-report.md`
- `/Users/ze/wenjin/.tmp/product-audit-20260619-round2/*.png`

当前产品方向正确：Wenjin 是证据驱动的科研工作台，Prism 和 Admin 已经接近系统级工具风格。但 Workbench 默认体验仍偏运行控制台，暴露了过多内部词、图标入口、候选/证据/审阅概念和中间态，导致用户不能稳定感知“专家团队可靠地产出可审阅证据”。

本次修复目标不是继续加能力，而是收敛体验叙事、信息架构和 SSOT 管理方式。

## 2. 总目标

1. 让用户进入 Workbench 后能立即理解：
   - 当前目标是什么。
   - 哪些专家正在/已经参与。
   - 已产生哪些证据和结果。
   - 哪些内容需要确认。
   - 下一步该做什么。
2. 默认界面不暴露内部运行协议、schema、DataService、Sandbox、tool name、node id。
3. 候选结果、资料库、审阅确认形成闭环，用户不会疑惑“刚搜到的东西去哪了”。
4. Admin 成为安全可管理的 SSOT 控制面，而不是手写 JSON/YAML 的工程面板。
5. 桌面体验稳定，移动端至少可读、可确认、可跳转，不出现横向溢出。

## 3. 非目标

1. 不重做整体视觉语言。继续沿用 `docs/current/wenjin-research-navigation-uiux.md` 的 System-Grade Research Workbench 方向。
2. 不新增第二套 execution 状态源。执行展示仍以 `frontend/lib/execution-run-view.ts` 为投影事实源。
3. 不绕过 Chat Agent -> Lead Agent pipeline。
4. 不把 Sandbox 做成用户可操作 room。Sandbox 仅在诊断或实验记录中只读展示。
5. 不在本轮重新设计模型调用、计费规则或 capability schema 的后端大结构，只做 UI 管理体验和投影收敛。

## 4. 问题聚合

### P0-A. Workbench 默认叙事不收敛

证据：

- `07-workspace-main.png`
- `34-workbench-current-candidates.png`
- `35-workbench-top-icon-1.png`
- `37-workbench-top-icon-3.png`
- `38-workbench-top-review.png`

现象：

- 用户同时看到 chat、run、候选、证据、审阅、过程、Sandbox、徽标数字和多个图标入口。
- 页面表达更像运行系统，而不是专家团队工作台。
- 顶部 icon tab 需要学习成本，新用户不知道数字和图标代表什么。

修复方向：

- Workbench 默认只保留三类主面：
  1. `总览`：当前目标、专家团队、关键进展、下一步动作。
  2. `证据`：候选文献、文档、实验产物、来源详情。
  3. `待确认`：用户需要保存、排除、应用或继续处理的结果。
- `进展` 仅在运行中突出显示；完成后收进总览的“查看过程”。
- `诊断` 放在 overflow / detail drawer，只给高级排查使用。
- `Sandbox` 不作为默认 tab 出现；仅当存在 sandbox artifact 时显示为 `实验记录`，并作为证据/诊断的子类。

验收标准：

- 默认 Workbench 首屏不出现 `Sandbox` tab。
- 顶部 active tab 必须有中文文字；非 active icon 必须有 tooltip 和 aria-label。
- 完成态默认落在 `待确认` 或 `证据`，不落在内部过程视图。
- `总览` 能在不打开详情的情况下回答“谁做了什么、产出了什么、还差什么”。

### P0-B. 内部协议和工程词泄露

证据：

- Chat 中可见 `launch_feature`。
- Workbench 结果编辑可见 `DataService rooms`。
- 旧错误直接显示 Feature 不可用。
- 默认 UI 出现 Sandbox、schema/id 风格文案。

禁止默认展示的词：

- `launch_feature`
- `DataService`
- `Sandbox`，除非位于诊断或后台上下文
- raw `feature_id` / `capability_id` / `node_id`
- `quality gate` / `质量门`
- `projection` / `hydration` / `focus id`
- raw schema 名，如 `*.v1`

修复方向：

- Chat block、ResultCard、LiveWorkflowPanel、ResultEditor 统一走 user-facing copy mapper。
- 诊断层可保留内部字段，但入口必须明确为“诊断详情”。
- 后端 summary 若仍生成“质量门”，前端必须映射为“风险项”或“待确认风险”。

验收标准：

- 主用户链路截图中不出现上述禁止词。
- 失败态使用“需要补充信息 / 任务未完整完成 / 部分结果可预览 / 建议重试”。
- 内部错误必须转译为用户行动建议，并保留 debug id 仅在诊断中显示。

### P0-C. 候选结果与资料库断层

证据：

- `09-library-sources-room.png`：资料库为空。
- `34-workbench-current-candidates.png`：Workbench 已有 20 篇候选文献。

现象：

- 用户可能认为检索结果消失。
- 候选结果和正式 Library 条目的关系不清楚。

修复方向：

- 引入统一的候选状态文案：
  - `待确认`
  - `已保存到资料库`
  - `已排除`
  - `保存失败`
- Library 空态如果存在 pending candidate，显示桥接提示：
  - “当前有 20 篇候选文献尚未保存。”
  - CTA：`查看候选文献`
- Evidence detail 显示：
  - 来源平台 provider
  - source URL / DOI
  - retrieved_at
  - save state
  - 是否已进入 Library

验收标准：

- 候选结果未保存时，Library 不再只显示空态。
- 保存候选后，Workbench candidate 状态和 Library count 同步刷新。
- 用户能从任一候选文献跳到对应详情并看到来源 URL。

### P0-D. ResultCard / 右侧待确认 / Commit 动作不统一

现象：

- Chat 侧出现“保存到工作区 / 查看详情 / 暂不保存”。
- 右侧也有“全部接受 / 保存已勾选 / 更多操作”。
- 用户可能不知道哪个动作才是最终写入。

修复方向：

- CommitActionBar 成为唯一确认动作组件。
- Chat ResultCard 默认只提供：
  - `查看并确认`
  - `稍后处理`
- `全部接受` 只在所有结果状态安全、无 partial/failure/risk 时显示。
- partial run 默认不显示一键全收，只显示 `保存已勾选`。

验收标准：

- 同一个 result set 不出现两套保存语义。
- partial / failed_partial / quality risk 状态下不会显示无条件 `全部接受`。
- 接受后通过 canonical refresh targets 更新 room / Prism / activity。

### P0-E. 质量门、异常、部分完成表达过重且不可行动

证据：

- `37-workbench-top-icon-3.png`

现象：

- 用户看到“未完成”“异常”“20 个质量门不通过”，但不知道影响范围。

修复方向：

- 把 quality gate 映射为风险摘要：
  - `引用支撑不足`
  - `来源信息不完整`
  - `部分专家未完成`
  - `实验结果待复核`
- 每类风险必须带 next action：
  - `补充材料`
  - `重试该专家`
  - `先保存可用证据`
  - `查看诊断`
- 成员异常聚合显示，不逐条刷红。

验收标准：

- 进展页默认不显示 gate id。
- 风险摘要能说明“是否影响当前可预览结果”。
- 至少支持对失败成员展示一个可理解的下一步动作。

## 5. P1 问题

### P1-A. 专家团队表达还不够产品化

目标形态：

- 总览展示专家 roster：
  - 专家名
  - 角色
  - 当前阶段
  - 最新思考摘录
  - 产出数量
  - 风险数量
- 点击专家后进入专家详情：
  - 阶段摘录 timeline
  - 关键证据
  - 产出预览
  - 风险/下一步

约束：

- 专家动态摘录继续使用 `RunViewTeamMemberSnapshot` / `RunViewTeamMemberPreviewItem`。
- 不新增前端事实源；只扩展投影与展示。
- `effectiveTools` / `effectiveSkills` 默认不展示，进入诊断层。

验收标准：

- 用户能从总览看到每个专家的当前判断，而不是节点 id。
- 同一个专家多阶段摘录能动态更新。
- 点击专家详情后可以预览该专家产出的文档、证据或实验项。

### P1-B. Workspace 创建与列表体验偏内部

问题：

- 创建工作区仍是表单，不像科研意图启动。
- 工作区搜索后标题计数和过滤结果不一致。
- 列表里测试数据噪声重。

修复方向：

- 创建弹窗默认改为一句话入口：
  - “我想写一篇联邦大模型的 AAAI 论文。”
- 系统根据用户描述建议：
  - workspace type
  - discipline
  - title
  - first task
- 高级字段折叠，不取消。
- 搜索时显示过滤计数，例如“找到 2 个匹配工作区 / 共 22 个”。
- 增加 archived / recent / pinned / test-hidden 的列表组织能力，至少先做 UI 层分组。

验收标准：

- 只填标题但缺字段时，按钮旁明确说明缺什么。
- 搜索结果计数不再误导。
- 移动端新建按钮不被截断。

### P1-C. Admin SSOT 过于工程化

问题：

- 定价策略默认显示 JSON。
- Capability/Skill 编辑直接暴露 YAML/JSON。
- 模型列表有“未绑定定价”，但风险不突出。

修复方向：

- 模型管理：
  - API key 不回显原文，只允许输入新值。
  - Base URL / Model Name / headers 有清楚说明。
  - 未绑定定价显示 warning，并说明实际生效策略。
  - 测试连接只显示安全摘要。
- 定价管理：
  - 增加结构化字段。
  - 增加 token -> credits 试算器。
  - 增加毛利估算。
  - JSON 作为高级模式。
- Capability / Skill：
  - 保存前 schema 校验。
  - 保存前 diff preview。
  - 保存前 impact summary：影响 workspace type、capability、skill、专家模板。
  - 操作日志记录变更。

验收标准：

- 管理员可以不手写 JSON 完成常见定价配置。
- 错误 JSON/YAML 不能保存。
- 重要配置保存前有 diff 和影响范围。

## 6. P2 问题

### P2-A. 文案和语言一致性

修复方向：

- 前台默认全中文。
- 英文只保留：
  - 品牌名
  - 模型名
  - API 字段
  - 论文标题/作者/venue
- `Library` 前台统一为 `资料库` 或 `文献资料`，不要混用。
- Admin 可保留英文 id，但加中文说明。

验收标准：

- Library 空态不再出现英文 “No library items found”。
- Admin 技术字段有中文解释或 tooltip。

### P2-B. Prism AI 面板继续减负

现状：

- Prism 体验整体较好，但 AI 面板在移动端和小屏上仍可能遮挡正文。

修复方向：

- 移动端 AI 面板改 bottom sheet。
- 桌面浮动面板支持停靠/最小化/恢复。
- 文案保持“直接说你想怎么改”，不暴露同步/异步技术词。

验收标准：

- 编译不会自动弹出 AI 面板。
- AI 面板不会遮住主要编辑动作。

## 7. 响应式与可访问性

### 响应式

问题证据：

- `31-mobile-workbench.png`
- `32-mobile-workspaces.png`
- `20-prism-mobile-clean-tab.png`

修复方向：

- `<= 768px`：
  - Workbench 改 list-first。
  - 结果详情改全屏 detail screen。
  - 顶部 header 只保留核心动作。
  - Prism 文件、编辑、PDF、AI 面板互斥展示。
- `769px - 1100px`：
  - Workbench 保留双栏，但 detail pane 可以折叠。
  - 次级 tab 使用 icon + tooltip，active 保留文字。

验收标准：

- 移动端不出现横向滚动。
- 长标题、URL、作者不撑破布局。
- 关键 CTA 不被截断。

### 可访问性

修复方向：

- Modal / drawer / fullscreen preview：
  - `aria-modal`
  - focus trap
  - 背景 inert
  - ESC 关闭
- Icon-only button：
  - `aria-label`
  - `title` 或 tooltip
- 状态变化：
  - run started / completed / failed 使用 polite live region。

验收标准：

- 打开创建工作区弹窗后，读屏和 Tab 顺序不会进入背景 workspace cards。
- 资料库 drawer 打开后，焦点不会落回 chat。
- 所有 icon-only 控件有可读名称。

## 8. 架构约束

1. `frontend/lib/execution-run-view.ts` 继续是 execution UX 投影事实源。
2. `frontend/stores/run-ui-store.ts` 只保存 focus / badge / selected preview，不保存执行事实。
3. LiveWorkflowPanel 只消费 `RunView`、workspace room projections、result preview projections，不自行派生第二套状态。
4. Candidate save state 必须来自 execution outputs / review items / room counts 的 canonical projection。
5. Admin capability / skill / model / credit 配置以 DataService 为 SSOT。
6. 不为旧字段新增兼容层；如果需要新字段，直接迁移到 canonical contract。
7. 技术诊断可以存在，但必须通过明确的诊断入口进入，不在默认用户路径展示。

## 9. 主要代码落点

### 前端 Workbench

- `frontend/app/(workbench)/workspaces/[id]/components/LiveWorkflowPanel.tsx`
- `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/WorkbenchHeader.tsx`
- `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/OverviewView.tsx`
- `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/EvidenceView.tsx`
- `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/ReviewView.tsx`
- `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/RunView.tsx`
- `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/ResultEditor.tsx`
- `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/utils.ts`
- `frontend/lib/execution-run-view.ts`

### Result / Commit

- `frontend/app/(workbench)/workspaces/[id]/components/ResultCard.tsx`
- `frontend/app/(workbench)/workspaces/[id]/components/CompletedView.tsx`
- `frontend/app/(workbench)/workspaces/[id]/components/result-preview/CommitActionBar.tsx`
- `frontend/app/(workbench)/workspaces/[id]/components/result-preview/ResultPreviewList.tsx`
- `frontend/app/(workbench)/workspaces/[id]/components/result-preview/ResultPreviewDetail.tsx`
- `frontend/lib/workbench-result-editing.ts`
- `frontend/hooks/useWorkspaceEventStream.ts`

### Rooms / Library

- `frontend/app/(workbench)/workspaces/[id]/components/rooms/LibraryDrawer.tsx`
- `frontend/app/(workbench)/workspaces/[id]/components/shell/WorkspaceHubDrawer.tsx`
- `frontend/app/(workbench)/workspaces/[id]/components/shell/WorkspaceChrome.tsx`
- `frontend/app/(workbench)/workspaces/[id]/components/shell/useWorkspaceChromeCounts.ts`

### Workspace Entry

- `frontend/app/(workbench)/workspaces/page.tsx` or corresponding workspace list component.
- workspace creation modal component.

### Admin

- Admin model management page.
- Admin credit pricing page.
- Admin capability management page.
- Admin skill management page.
- DataService admin routers for validation / preview / audit if missing.

### Backend Projection / Copy

- `backend/src/agents/lead_agent/v2/team/kernel.py`
- `backend/src/agents/lead_agent/v2/team/quality_gates.py`
- `backend/src/contracts/team_presentation.py`
- `backend/src/agents/contracts/task_report.py`
- `backend/src/services/execution_commit_service.py`
- execution API projection services.

## 10. 分阶段实施计划

### Phase 1: P0 Workbench 收敛

目标：默认路径先干净。

工作项：

1. 重构 WorkbenchHeader tab：
   - 默认 `总览 / 证据 / 待确认`
   - `进展` 条件显示
   - `诊断` 进入 overflow
2. ResultEditor 去掉 `DataService rooms` 文案。
3. EvidenceView 移除默认 Sandbox tab，改为条件 `实验记录`。
4. Chat/ResultCard 屏蔽 tool name 和内部错误。
5. CommitActionBar 统一 result commit 文案和 partial 策略。
6. Quality gate copy mapper 上线。

验证：

- `npm run typecheck`
- `npx vitest run frontend/tests/unit/v2/LiveWorkflowPanel.test.tsx frontend/tests/unit/v2/ResultCard.test.tsx frontend/tests/unit/ui/commit-action-bar.test.tsx`
- 浏览器跑：发起文献定位 -> 完成 -> 查看证据 -> 保存候选 -> 打开资料库。

### Phase 2: Evidence / Library 闭环

目标：用户知道候选结果和资料库的关系。

工作项：

1. Candidate save state projection。
2. Library pending candidate bridge empty state。
3. Evidence detail metadata：provider、retrieved_at、source URL、save state。
4. 保存后刷新候选状态、room count、Prism refs。

验证：

- 保存单个候选。
- 保存全部安全候选。
- 排除候选。
- Library 空态和非空态。

### Phase 3: 专家团队表达

目标：让团队实名制成为默认信任面。

工作项：

1. Overview roster 使用 snapshots 和 previewItems。
2. Expert detail screen。
3. 成员异常聚合。
4. 工具/skill 列表移入诊断。

验证：

- 运行中动态更新摘录。
- 完成后每个专家可查看产出预览。
- 失败成员展示下一步。

### Phase 4: Admin SSOT 安全化

目标：后台配置可控、可校验、可解释。

工作项：

1. 模型管理安全提示和定价绑定状态。
2. 定价结构化表单与试算器。
3. Capability/Skill schema validate + diff + impact summary。
4. 操作日志补足。

验证：

- 新增模型不暴露 API key。
- 错误定价配置不能保存。
- capability 编辑前能看到 diff 和影响范围。

### Phase 5: 响应式与可访问性

目标：移动端不破，可访问性不挡路。

工作项：

1. Workbench mobile list-first。
2. Workspace list mobile CTA 修复。
3. Prism AI mobile bottom sheet。
4. Modal/drawer focus trap 和 inert。
5. Icon-only aria-label/tooltip 补全。

验证：

- 390x844 Workbench。
- 390x844 Workspace list。
- 390x844 Prism。
- 键盘 Tab/ESC smoke。

## 11. 测试矩阵

### 单元测试

- RunView projection：
  - completed / failed_partial / sandbox artifacts / prism review items
  - team snapshots / preview items / quality highlights
- Result commit：
  - partial 不显示无条件全部接受
  - save selected / accept all / reject
- Evidence filtering：
  - all / literature / document / memory / experiment
  - saved / pending / excluded
- Admin validation：
  - model secret masking
  - pricing config validation
  - capability/skill schema invalid

### 浏览器 smoke

1. 创建 workspace。
2. 输入“联邦大模型微调，目标 AAAI”。
3. Chat Agent 澄清或启动 capability。
4. 右侧总览显示团队和进展。
5. 完成后进入证据/待确认。
6. 打开文献详情，确认来源。
7. 保存候选到资料库。
8. 打开资料库，看到已保存条目。
9. 切到 Prism，不触发登录页，不自动弹 AI 面板。
10. Admin 打开模型、定价、capability、skill，不暴露密钥原文。
11. 390x844 跑工作区列表、Workbench、Prism。

## 12. Definition of Done

1. 默认用户路径无内部词泄露。
2. Workbench 默认三主面收敛完成。
3. 候选结果和资料库状态闭环。
4. partial / risk 状态不会诱导一键全收。
5. 专家团队在总览中作为责任面出现。
6. Admin 常见配置不需要直接手写 JSON。
7. 移动端无横向溢出。
8. 关键 modal/drawer 具备 focus trap、inert、ESC close。
9. 文档事实源更新：
   - `docs/current/wenjin-research-navigation-uiux.md`
   - `docs/current/workspace-current-state.md`
   - `docs/current/frontend-feature-plugin-contract.md`
   - `docs/current/workspace-feature-catalog.md`，如 capability/skill 展示契约变化。

## 13. 实施优先级建议

最优先做 Phase 1 + Phase 2。它们直接解决用户当前看到的主要问题：Workbench 太复杂、内部词泄露、候选结果和资料库断层、保存动作不统一。Phase 3 可以紧随其后，把“团队实名制”真正产品化。Admin 和响应式重要，但可以在前台主链路稳定后推进。
