# System-Grade Research Workbench UIUX Design

> 状态：已定稿，作为 Wenjin 全站视觉推广基准  
> 日期：2026-06-04  
> 范围：Landing、Auth、Workspace list、Workbench、Rooms、Prism、Admin/DataService、共享 UI 组件  
> 目标：把 Wenjin 从多套混杂视觉收敛为一个可信、克制、可审计、适合长时间科研工作的系统级研究工作台。

## 1. 定位

Wenjin 的界面基准定为 **System-Grade Research Workbench**。

它不是营销型 SaaS，也不是装饰型 glass UI。它应该像一个“研究操作系统 / 可信浏览器壳”：平时框架尽量隐形，把注意力交给研究内容；当涉及证据、权限、sandbox、质量门、commit、团队责任归属时，系统框架必须明确、可信、可追踪。

参考方向：

- Apple：材质表达层级，但不能牺牲可读性；动效只服务状态反馈和空间关系。
- OpenAI：克制排版、几何精确、温和但不幼稚。
- Chrome：框架几乎隐形，但可信 UI 和安全状态必须显性。
- OxSci：机构级深蓝、白底、轻边框、8px 圆角、学术可信感。

## 2. 设计原则

1. **Evidence over decoration**  
   证据、审阅、产出归属、质量门，比 glow、渐变、装饰图形更重要。

2. **Trusted chrome, quiet content**  
   顶层 shell 承担身份、状态、导航、权限和任务入口；内容区域保持安静、清晰、低噪声。

3. **Chat for intent, workbench for work**  
   左侧 chat 只负责目标、约束、材料和必要干预；右侧承载团队执行、证据链、结果审阅和 Prism 写入。

4. **Review before commit**  
   所有 agent 输出先进入 review queue / result card / Prism diff，用户确认后写入 rooms。

5. **Agent team as responsibility surface**  
   团队实名制不做卡通角色，也不做头像秀。它展示成员职责、模板、状态、工具/技能、产出归属、质量门和证据关联。

6. **Quiet density**  
   长流程科研任务需要稳定布局、受控文字、紧凑但不拥挤的信息层级。禁止卡片套卡片和无意义大留白进入工作台。

## 3. 全局视觉基准

### 3.1 色彩

新代码只使用 `--wjn-*` 语义 token。旧 `--brand-*`、`--compute-*`、`--glass-*`、`--v2-*` 只作为迁移 alias 暂存，不得作为新组件设计语言。

主色：

- `--wjn-navy`: `#0f1f35`，顶层 trusted chrome、主按钮、关键标题。
- `--wjn-blue`: `#2c5da0`，当前运行、焦点、品牌锚点。
- `--wjn-gold`: `#e7b008`，仅用于极少量针脚式强调、推荐、关键确认，不做大面积按钮色。

语义色：

- `--wjn-evidence`: `#0f766e`，证据、通过、可追溯。
- `--wjn-review`: `#b45309`，待审阅、需确认。
- `--wjn-success`: `#15803d`，已保存、成功。
- `--wjn-error`: `#b91c1c`，失败、危险操作。

背景与边框：

- 冷白、浅灰、浅蓝灰为主。
- 页面 shell 允许极轻径向蓝/青材质光，但不能出现离散光球、紫蓝霓虹或高饱和大渐变。
- 1px hairline 是默认分隔方式。

### 3.2 材质

材质只用于表达层级：

- 顶栏、侧栏、drawer、floating command bar 可以使用轻度 translucent material。
- 正文卡片、表格、证据、审阅队列使用实体白底或非常轻的 raised white。
- 不再使用 LiquidGlassCard 作为新界面主容器。
- 禁止大面积 backdrop blur 叠加导致内容可读性下降。

### 3.3 圆角与阴影

- 控件：8px 到 10px。
- 系统 chrome、command bar、重要 panel：12px 到 16px。
- 不使用 24px 以上圆角作为默认卡片形状。
- 阴影只用于浮层或重要 panel；列表项和普通卡片以边框为主。

### 3.4 字体与排版

- 主字体继续使用系统 sans，兼容中文长时间阅读。
- 标题短、重、精确：避免营销式大 headline 进入工作台。
- 数字、计时、token、积分、节点数量使用 tabular nums。
- uppercase label 可用于系统层级标识，例如 `TRUSTED EXECUTION`、`EVIDENCE LEDGER`，但数量受控。
- 不使用科幻字体、古风字体、负责任务外的装饰字形。

### 3.5 动效

动效只表达：

- hover / active 的轻微反馈。
- progress / status 的状态变化。
- drawer / modal / command bar 的空间关系。

规则：

- 常规 microinteraction：140ms 到 220ms。
- drawer/modal：180ms 到 260ms。
- 禁止循环光效、跳动角色、装饰性漂浮动画。
- `prefers-reduced-motion` 必须关闭非必要动画。

## 4. 页面母版

### 4.1 Public / Entry Template

适用：Landing、Auth、Pricing、Workspace list 空状态。

特征：

- 机构级白底 + 深蓝顶栏。
- hero 可以大留白，但第一屏必须展示产品真实能力或工作流入口。
- 使用路径卡表达 workspace type / workflow start，不做营销堆叠。
- public 页可以更“展示”，但仍不使用紫蓝光球和 glass cards。

### 4.2 Workbench Template

适用：workspace `/workspaces/[id]` 主界面。

结构：

- 顶层 trusted chrome：workspace identity、surface switch、rooms、command bar、team/status summary。
- 左侧 chat：意图、约束、材料、干预。
- 右侧 execution board：overview、run、evidence、review。
- room drawers：ledger/store 风格，不像聊天延伸。

关键交互：

- Command bar 是高级入口，统一 workflow 搜索、room 跳转、团队招募、快捷任务启动。
- 当前运行自动聚焦 execution board。
- 有 staged output 时自动提示 review queue。
- 用户手动导航是临时行为，不暴露内部 focus/lock 概念。

### 4.3 Prism Template

适用：LaTeX/Prism 编辑、PDF preview、review diff。

结构：

- Project bar 显示稿件身份、编译状态、review queue。
- Editor/PDF/Inspector 采用系统级分栏。
- Prism diff 必须显示 agent 责任归属和证据来源。
- 写入前必须保持可审阅、可撤销、可追溯。

### 4.4 Admin / DataService Template

适用：管理员后台、模型管理、积分定价、capability、skills、analytics。

结构：

- 更高信息密度。
- 使用 metric row、module cards、tables、detail drawers。
- 低频操作进入 overflow / dialog。
- 危险操作使用明确红色和二次确认。

Admin 的视觉目标是“控制台”，不是 landing 页，也不是 glass dashboard。

## 5. 团队实名制 Agent 前端

团队 agent 前端表达为 **Research Team / 执行委员会 / 值班台**。

必须展示：

- 成员显示名，例如“文献专家”“实验工程师”“证据审稿人”“学术编辑”。
- template id / capability id。
- 当前状态：queued、running、passed、review、failed。
- 职责摘要。
- effective tools / skills 的精简展示。
- 输出归属：产物、证据、Prism diff、review item。
- quality gates：证据追溯、覆盖深度、复现性、写作一致性等。

不展示：

- 卡通头像。
- 角色口头禅。
- 拟人化表演动画。
- 无产出归属的“团队成员卡片”。

## 6. 组件迁移策略

### 6.1 Token 收敛

`frontend/app/globals.css` 应收敛为：

- `--wjn-*` 为唯一新组件 token。
- `--v2-*` 映射到 `--wjn-*`，仅保证旧组件过渡。
- `--brand-*`、`--compute-*`、`--glass-*` 逐步移除或只保留兼容注释。

### 6.2 Shared UI

优先更新：

- `frontend/components/ui/button.tsx`
- `frontend/components/ui/card.tsx`
- `frontend/components/ui/badge.tsx`
- `frontend/components/layout/header.tsx`
- `frontend/components/workspace/WorkspaceSurfaceState.tsx`

共享组件必须提供统一视觉基础，避免每个页面写自己的视觉系统。

### 6.3 Page Rollout Order

推荐顺序：

1. Global tokens + shared UI。
2. Header / landing / auth / workspace list。
3. Workbench shell + LiveWorkflowPanel + team roster。
4. Rooms drawers + review queue + run history。
5. Prism editor / inspector / review list。
6. Admin/DataService console。
7. 清理旧 glass / brand / compute 样式债务。

## 7. 可访问性与响应式

- 所有 icon-only 按钮必须有 `aria-label` 或 tooltip。
- 文本不得在按钮、卡片、chip 中溢出。
- 窄屏优先 list-first，详情进入 drawer/fullscreen。
- 导航先折叠，内容后折叠。
- `prefers-reduced-motion` 全局生效。
- 色彩不能成为唯一状态表达，必须配合文字或图标。

## 8. 验证标准

视觉推广完成后必须通过：

- `frontend npm run typecheck`
- `frontend npm run build`
- `frontend npx vitest run`（如时间允许至少覆盖相关 UI projection/store tests）
- 浏览器验证：
  - Landing
  - Login/Register
  - Workspace list
  - Workbench
  - LiveWorkflowPanel run/evidence/review
  - Team roster
  - Prism
  - Admin dashboard / DataService pages
- 颜色扫描：新改组件不得引入大面积 purple、glass orb、古风 paper/ink、无意义 brown/tan palette。

## 9. 非目标

- 不重写后端 agent 架构。
- 不改变 block protocol、execution projection、room commit contract。
- 不改变 billing / sandbox / model routing 业务逻辑。
- 不把所有页面强行做成一样的密度。
- 不追求 Apple/OpenAI/Chrome 的品牌复刻，只吸收其系统级克制、可信框架和成熟层级。
