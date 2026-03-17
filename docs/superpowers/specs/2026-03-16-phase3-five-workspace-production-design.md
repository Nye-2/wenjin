# Phase 3: 五个 Workspace 生产可用上线设计文档

> **状态**: Draft（待用户审阅）
> **目标上线日期**: 2026-04-01（五个 workspace 同日全量上线）
> **适用范围**: thesis / sci / proposal / software_copyright / patent

## 1. 背景与目标

在 Phase 1/Phase 2（功能恢复 + 治理收口）基础上，Phase 3 的核心目标是：

1. 五个 workspace 在 2026-04-01 同日全量对真实用户开放。
2. 每个 workspace 达到“真实可用”质量标准，而不是演示态闭环。
3. 同步提升 UI/UX，降低真实用户上手与失败恢复成本。
4. `thesis` 与 `sci` 采用分离实现，便于后续独立调试和快速迭代。

## 2. 关键产品决策（已确认）

1. `thesis` 与 `sci` **不共用一套业务流水线**。
   - 可复用基础设施（task、artifact、dashboard、计费、监控）。
   - 不复用业务生成逻辑（prompt、模板、规则、状态机）。
2. 论文输出语言硬约束：
   - `thesis`: 固定中文输出。
   - `sci`: 固定英文输出。
3. 前端中英切换保留，仅影响 UI 文案，不影响论文生成语言。

## 3. 范围定义

### 3.1 In Scope

1. 子项目 A：五个 workspace 业务闭环达标。
2. 子项目 B：跨 workspace UI/UX 基线统一升级。
3. 子项目 C：发布质量门禁、监控、回滚预案落地。

### 3.2 Out of Scope

1. 新增 workspace 类型。
2. 与上线目标无关的基础架构重写。
3. 大规模视觉重设计（只做质量与体验关键提升）。

## 4. 子项目 A：业务闭环达标

## 4.1 Workspace 交付矩阵

| Workspace | 必达 Feature | 语言约束 | 核心上线判定 |
|---|---|---|---|
| thesis | thesis_writing / figure_generation / compile_export | 中文 | 可完成“写作 -> 配图 -> 编译导出”完整路径 |
| sci | literature_search / paper_analysis / writing | 英文 | 可完成“检索 -> 分析 -> 写作输出”完整路径 |
| proposal | proposal_outline / background_research / budget-risk(min) | 中文优先 | 可产出可编辑申报书主骨架 |
| software_copyright | technical_description / copyright_materials / export-list(min) | 中文 | 可产出登记材料完整包 |
| patent | patent_outline / prior_art_search / novelty-risk(min) | 中文 | 可产出专利框架与现有技术对比结论 |

## 4.2 闭环统一标准

所有必达 feature 均需满足：

`execute -> task -> artifact -> dashboard -> page result`

并满足：

1. 任务进度可观测（至少 pending/running/success/failed）。
2. 结果可复查（artifact 内容结构化，包含生成模式与时间信息）。
3. 失败可恢复（页面有重试或修正参数后重试入口）。

## 4.3 thesis 与 sci 分离实现原则

1. `thesis`：毕业论文规范驱动，中文模板与章节结构固定度更高。
2. `sci`：投稿论文规范驱动，英文输出与实验结构完整性优先。
3. 不抽象“统一 paper pipeline 业务层”。
   - 避免 profile 共享导致调试耦合。
   - 保持独立测试矩阵，快速定位回归。

## 5. 子项目 B：UI/UX 统一升级

## 5.1 跨 workspace 统一体验基线

1. 状态体验统一：空态、加载态、失败态、重试态、长任务进度态。
2. 结果页统一：摘要区、结构区、后续动作区。
3. 新手引导统一：输入示例、输出预期、失败后的下一步。
4. 文案统一：重要状态短句风格一致，避免误导（尤其 failed/in_progress）。

## 5.2 关键体验验收

1. 用户首次进入任一 workspace，30 秒内知道如何开始。
2. 任一失败场景，用户可在当前页完成恢复，不依赖刷新或跳转隐藏入口。
3. 长任务阶段有明确阶段文本和进度反馈。

## 6. 子项目 C：发布与质量门禁

## 6.1 质量门禁（必须全部通过）

1. 后端核心回归：workspace feature handlers / routers / dashboard。
2. 前端类型检查：`npx tsc --noEmit`。
3. 五个 workspace 各至少 1 条端到端主链路回归。
4. 计费与任务治理回归（幂等、防重复扣费、queue submit failure）。

## 6.2 生产发布准备

1. 监控项：任务失败率、任务耗时、关键 feature 成功率、5xx 错误率。
2. 告警阈值：按 workspace 与 feature 维度分桶。
3. 回滚预案：一键回滚版本 + 数据兼容说明 + 用户公告模板。

## 7. 时间计划（绝对日期）

| 日期区间 | 里程碑 |
|---|---|
| 2026-03-16 ~ 2026-03-20 | thesis/sci 独立链路打通与语言硬约束落地 |
| 2026-03-21 ~ 2026-03-24 | proposal/software_copyright/patent 核心闭环达标 |
| 2026-03-25 ~ 2026-03-27 | UI/UX 统一基线改造完成 |
| 2026-03-28 ~ 2026-03-30 | 全量回归、性能修正、发布演练 |
| 2026-03-31 | 发布冻结与最终 Go/No-Go 评审 |
| 2026-04-01 | 五个 workspace 同日全量上线 |

## 8. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| 五 workspace 并行导致质量波动 | 同日上线失败风险上升 | 按 workspace 设独立 owner + 每日红线回归 |
| thesis/sci 分离后重复劳动增加 | 开发效率下降 | 只复用基础设施层与 UI 组件层 |
| UI/UX 改造影响既有页面稳定性 | 回归成本上升 | 状态组件抽象统一 + 逐页替换 |
| 上线前缺少真实流量验证 | 生产故障不可预估 | 3/30 完成流量模拟与发布演练 |

## 9. 验收标准（DoD）

1. 五个 workspace 全部达到至少 2 个真实闭环 feature（表中必达项）。
2. thesis 输出固定中文、sci 输出固定英文，并在后端逻辑中强制。
3. UI/UX 基线（空/加载/失败/重试/进度）覆盖所有 workspace 主页面。
4. 质量门禁通过并完成 2026-03-31 Go/No-Go 评审。
5. 2026-04-01 同日全量上线完成。

## 10. 与前序文档关系

1. 本文是 `full-recovery` 之后的下一阶段（Phase 3）扩展。
2. 与以下文档配套：
   - `docs/superpowers/specs/2026-03-16-full-recovery-design.md`
   - `docs/superpowers/plans/2026-03-16-full-recovery-implementation-plan.md`
3. Phase 3 的实施细节见配套计划文档：
   - `docs/superpowers/plans/2026-03-16-phase3-five-workspace-production-plan.md`
