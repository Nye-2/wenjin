# Phase 3 交接文档（给 Claude Code 直接执行）

> 日期：2026-03-16  
> 当前阶段：Phase 3（五个 workspace 生产可用上线）  
> 目标上线日：2026-04-01（五个 workspace 同日全量上线）

## 1. 执行目标与硬约束

请严格按以下约束执行，优先级从高到低：

1. 只做 Phase 3 范围内工作，不扩展新 workspace，不做无关重构。
2. `thesis` 与 `sci` 分开实现，不共用业务流水线（可复用基础设施与通用组件）。
3. 输出语言硬约束：
   - `thesis` 论文输出固定中文；
   - `sci` 论文输出固定英文。
4. 前端中英切换仅影响 UI 文案，不得影响论文输出语言。
5. 当前仓库是脏工作区，存在大量无关改动。不得回滚或覆盖非本任务变更。
6. 本次只做落地实现，不要提交 commit（`git commit` 禁止执行）。

## 2. 开始前必须 Review 的两份文档

请先完整阅读并以其为准执行：

1. `docs/superpowers/specs/2026-03-16-phase3-five-workspace-production-design.md`
2. `docs/superpowers/plans/2026-03-16-phase3-five-workspace-production-plan.md`

如果实现中发现两份文档冲突，处理原则如下：

1. 以“用户已确认硬约束”为最高优先级（thesis/sci 分离 + 语言固定 + 2026-04-01 同日上线）。
2. 以设计文档为目标定义，以计划文档为执行拆解。
3. 有冲突点时先暂停并给出最小化决策选项，不自行改方向。

## 3. 当前仓库协作边界

1. 仅修改与你当前子任务直接相关文件。
2. 禁止执行任何破坏性命令（如 `git reset --hard`、`git checkout --`）。
3. 若发现任务过程中有新增“非你所做”的文件变化，先停下并报告。
4. 每完成一个任务块，输出：
   - 已改文件列表
   - 执行过的命令
   - 测试结果（通过/失败 + 失败原因）
   - 下一步计划

## 4. 分阶段执行顺序（按 A -> B -> C）

### 4.1 A：业务闭环（先做）

目标：五个 workspace 达到真实用户可用的核心闭环。

### A1. thesis/sci 分离 + 语言硬约束（最高优先）

1. 为 thesis/sci 分别落地独立服务逻辑与 handler 路径。
2. 增加/更新测试，明确断言：
   - thesis 输出语言为 `zh`；
   - sci 输出语言为 `en`。
3. 先写失败测试，再做最小实现，再跑通过。

### A2. proposal/software_copyright/patent 三线补齐闭环

1. 每个 workspace 至少打通 2 条真实 feature 闭环。
2. 闭环最低标准：`execute -> task -> artifact -> dashboard -> page result`。
3. artifact 需包含可复查信息（至少 generation_mode、schema_version、generated_at）。

### 4.2 B：UI/UX 统一基线（并行次优先）

目标：降低真实用户首次使用与失败恢复成本。

1. 统一状态体验：空态、加载态、失败态、重试态、长任务进度态。
2. 统一结果页信息层：摘要、结构分区、下一步动作。
3. 关键验收：
   - 新用户 30 秒内可理解如何开始；
   - 失败可在当前页面恢复，不依赖隐藏入口；
   - 长任务有明确阶段反馈。

### 4.3 C：发布质量门禁（上线前必须完成）

1. 落地 Go/No-Go 质量门禁（自动检查通过/失败）。
2. 覆盖后端核心回归、前端类型检查、workspace E2E 主链路、幂等/计费保护。
3. 输出上线演练清单与回滚预案（文档化）。

## 5. 每个任务块的标准执行模板（必须遵守）

1. 写失败测试（精确到行为断言）。
2. 运行测试并确认失败（保留失败信息摘要）。
3. 做最小实现（禁止顺手大改）。
4. 运行定向测试确认通过。
5. 运行相关回归（防止引入跨模块回归）。
6. 更新任务进度记录（不 commit，只汇报）。

## 6. 建议命令基线（可按需细化）

后端定向：

```bash
cd /home/cjz/AcademiaGPT-V2/backend
PYTHONPATH=. uv run pytest tests/workspace_features/test_workspace_e2e_matrix.py -v
```

后端发布门禁：

```bash
cd /home/cjz/AcademiaGPT-V2/backend
PYTHONPATH=. uv run pytest tests/services/test_release_gate.py -v
```

前端类型检查：

```bash
cd /home/cjz/AcademiaGPT-V2/frontend
npx tsc --noEmit
```

## 7. 阶段验收（DoD）

达到以下条件才算 Phase 3 可上线：

1. 五个 workspace 均具备可被真实用户连续使用的核心闭环。
2. `thesis=zh`、`sci=en` 在后端逻辑中被硬性约束，并有测试覆盖。
3. UI/UX 统一状态基线覆盖主流程页面。
4. 发布门禁检查可执行，且结果可用于 2026-03-31 的 Go/No-Go 评审。
5. 保持无提交（本轮由人工决定何时提交）。

## 8. 给 Claude Code 的执行起始指令（可直接复制）

请先阅读：

1. `docs/superpowers/specs/2026-03-16-phase3-five-workspace-production-design.md`
2. `docs/superpowers/plans/2026-03-16-phase3-five-workspace-production-plan.md`
3. `docs/superpowers/plans/2026-03-16-phase3-claudecode-handoff.md`（本文件）

然后从 A1（thesis/sci 分离 + 输出语言硬约束）开始实施。严格 TDD：先失败测试，再最小实现，再回归。当前仓库是脏工作区，请不要回滚任何无关改动，也不要执行 `git commit`。每完成一个任务块，按“改动文件 + 命令 + 测试结果 + 下一步”格式汇报。
