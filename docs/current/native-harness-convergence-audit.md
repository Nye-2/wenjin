# Native Harness Convergence Audit

更新时间：2026-06-08
状态：Current

本审计记录 Wenjin 自研 agent harness 相对 Codex / deer-flow 的吸收、取舍和剩余风险。结论不等于发布完成；它只说明当前 harness 是否已经沿正确方向收敛，以及下一轮应该优先补哪里。

## 1. 当前结论

Wenjin harness 已经能作为科研/写作/实验任务的自研执行基座继续推进，不需要接 Codex SDK、cc-switch 或 deer-flow runtime。

现在已经闭合的核心链路：

```text
Chat Agent
  -> launch_feature
  -> ExecutionRecord
  -> LeadAgentRuntime
  -> TeamKernel / static graph
  -> ReactSubagent
  -> Wenjin Harness
  -> DataService sandbox / execution / review
  -> RunView / ResultCard / Prism / rooms
```

当前实现没有新增第二套 execution table、harness run table、frontend harness store 或外部 agent runtime。生产代码扫描未发现 Codex SDK、cc-switch、deer-flow runtime 或 `sandbox.run_command` 依赖。

## 2. 已吸收的 Codex 模式

- **命令策略审计**：`backend/src/agents/harness/command_audit.py` 使用 argv-first 结构记录 `policy_decision(schema=wenjin.harness.command_policy_decision.v1)`，在创建 sandbox job 前阻断高风险命令、host path、protected/internal path 和不规范 pip spec。
- **bounded output**：大文件读取、搜索、Python stdout/stderr 和 diff 只给模型 bounded preview，完整内容外部化到 `/workspace/outputs/harness/**`，并作为内部 refs 进入 tool record / event。
- **文件变更证据**：`sandbox.write_file` / `sandbox.str_replace` 记录 hash + unified diff，节点聚合 `file_change_summary`，用户仍通过 review-first flow 接受结果。
- **运行证据而非文本猜测**：`execution_manifest`、`reproducibility_manifest`、`failure_classification`、`sandbox_execution_summary`、`reproducibility_summary`、`run_journal_summary` 都挂回 harness payload / `ExecutionNodeRecord.node_metadata.harness`，RunView 不解析 raw tool JSON；`report_markdown` 已包含用户可读的 Reproducibility 段落和依赖安装失败恢复建议。
- **明确失败边界**：unknown/forbidden tools 显式失败，不把工具型节点静默降级为 plain LLM。

未吸收的 Codex 部分是有意取舍：不引入 SDK、app-server/thread 模型、泛 shell、approval console 或 provider protocol bridge。

## 3. 已吸收的 deer-flow 模式

- **工具 substrate 边界**：harness 是 Lead/subagent 的工具执行层，不是新的 agent framework。
- **文件工具与 Python 工具组合**：内置 `sandbox.list_dir`、`glob`、`grep`、`read_file`、`write_file`、`str_replace`、`run_python`，并由 capability/skill policy 收窄。
- **工具异常可恢复**：ReactSubagent adapter 把普通 tool exception 降级为 structured JSON error result，保留 tool record 和 `execution.harness.tool_call.failed`。
- **loop guard**：重复工具调用会触发 warning/hard-stop 逻辑，且不破坏 provider tool-call pairing。
- **runtime journal 思路**：用 `run_journal_summary` 和 `journal` event envelope 给前端提供产品化进度摘要，而不是展示 debug payload。
- **bounded context**：`_harness_context(schema=wenjin.harness.context_bundle.v1)` 固定注入任务、workspace、sandbox 文件系统、dataset provenance、protected/internal paths、recent evidence 和可复现实验摘要。

未吸收的 deer-flow 部分也是有意取舍：不迁移 agent factory、thread-local workspace、完整 middleware stack、ACP surface 或 allow-all bash 工具。

## 4. Wenjin 自身的关键差异

- **一个 workspace 一个 sandbox**：DataService sandbox environment 按 `workspace-{workspace_id}` 复用，任务容器短生命周期，文件、venv、cache 持久化在 workspace sandbox。
- **能力/技能是业务事实源**：capability / skill / agent template 由 DataService catalog 管理，Lead/TeamKernel 动态加载；harness policy 只是执行权限边界。
- **review-first artifact**：Prism、rooms、sandbox artifacts 都先进入 review/result-card 流程，不直接覆盖用户材料。
- **团队实名制前端投影**：TeamKernel graph 只展示五步流程；实名成员、成员 activity 和质量门由 `frontend/lib/execution-run-view.ts` 从 hydrated node states/runtime_state 派生。
- **业务工具与 sandbox 工具同链路**：`library_read`、`document_read`、`memory_read`、`prism_read`、`citation_parser`、`artifact_create` 读取 bounded workspace snapshot 或返回 staged payload，不直接提交 rooms。

## 5. 本轮验证

已运行：

- `backend`: `.venv/bin/python -m pytest tests/agents/harness tests/agents/lead_agent/v2 tests/subagents/v2 tests/integration/test_harness_mock_sandbox_e2e.py -q` -> 269 passed
- `backend`: `.venv/bin/ruff check src/agents/harness src/agents/lead_agent/v2 src/subagents/v2 tests/agents/harness tests/agents/lead_agent/v2 tests/subagents/v2` -> passed
- `frontend`: `npm run typecheck` -> passed
- `frontend`: `npx vitest run tests/unit/lib/execution-run-view.test.ts tests/unit/v2/live-workflow-view-model.test.ts tests/unit/stores/execution-store.test.ts tests/unit/v2/latex-editor-prism-shell.test.tsx` -> 37 passed
- Docker local-build stack rebuilt; frontend production build passed.
- Browser smoke verified Workbench team task launch/result review, TeamKernel five-step progress, quality gate dedupe, Prism compile/PDF contrast, and Prism AI assist discoverability.

## 6. 剩余不足

### P1: 模型可靠性仍是最大产出瓶颈

当前 harness 能把工具、上下文、证据和输出边界组织起来，但最终 research synthesis / writing quality 仍强依赖模型。需要后续做针对性 eval：文献相关性、引用可核验、创新点可发表性、实验解释一致性、Prism 改稿是否保持 LaTeX 结构。

### P1: 来源质量和引用核验还不够硬

claim-source 绑定已经进入强制质量门：`claim_evidence_map_required` 会要求 supported claims 使用当前 workspace 的 `source_id` 或 `citation_key`。`source-quality-auditor` / `citation-auditor` 的输出也已经进入结构化质量门，不能只靠 prose 和 `quality_gates_checked` 通过；source authority、metadata completeness、weak support、fabricated citation、claim-source binding 和 style consistency gate 会要求 `citation_key_audit`、`missing_sources`、`fabrication_risks` 或 `bibtex_projection_notes`，其中的 citation/source refs 必须来自当前 workspace allowlist，且 `fabricated`、`not_ready`、`replace`、`missing`、`unsupported`、`weak` 或 high/critical/blocking risk 会触发修订。剩余不足是 DOI/BibTeX 深度自动校验、引用样式自动核验和把高风险 citation findings 进一步转成用户可审阅 review item。

### P1: sandbox 安装与实验体验仍偏基础

自动安装、缺包重试、command audit、`reproducibility_manifest` 和用户可读 `report_markdown` 已经具备；每次 `sandbox.run_python` 会留下脚本、依赖、sandbox job/environment、生成产物、命令风险摘要和安装失败恢复建议。`/workspace/datasets/manifest.json` 与 context-level `dataset_provenance` 已经打通：DataService source page asset 若显式位于 `/workspace/datasets/**`，会进入 bounded context，并在下一次 `sandbox.run_python` 执行前安全合并进 sandbox 内 dataset manifest，保留用户已有条目优先权；run payload、`reproducibility_manifest` 和 `report_markdown` 也会携带安全 dataset input 摘要。剩余不足是面向长程实验的更完整实验叙事模板，以及把这些证据更轻地展示到默认 UI 的方式。

### P2: TeamKernel 质量门显示还有压缩空间

默认团队面板已经按 gate id 聚合，不再把 23 条历史事件刷屏；但多个不同 gate 仍会映射成相同中文标签。后续可以把质量门按类别折叠为 `引文规范 x2`、`质量检查 x3` 这类更轻的展示。

### P2: 泛命令执行仍未开放

这是正确的安全边界，但也意味着 Codex 那种自由 shell harness 还没有完全覆盖。若以后开放 `sandbox.run_command`，必须先完成 DataService command policy、output budget、artifact discovery、kill/cancel 和审计 UI。

### P2: 前端执行展示复杂度上升

RunView 已经是唯一 presenter，但 Workbench / Runs drawer / Prism / ResultCard 的组合仍复杂。后续任何 UI 变更都应继续压到 `execution-run-view.ts` 或小型 presenter，不要重新在组件里拼 raw execution shape。

## 7. 诚恳判断

当前 Wenjin harness 已经摆脱“只能靠提示词让 subagent 干活”的阶段，具备了文件、Python、证据、review 和团队展示的基本闭环。它还不是 Codex 那种通用 coding agent harness，也不需要变成那样；对 Wenjin 的垂直科研/写作/实验场景，自研方向是更合适的。

下一阶段不要再追求接入外部 runtime。应该围绕质量闭环继续做：source verification、citation grounding、experiment reproducibility 报告化、Prism rewrite eval、team member prompt/tool contract 迭代，以及更轻的用户默认视图。
