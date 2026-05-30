# Workspace Mission Capability Catalog

更新时间: 2026-05-30
状态: Current
Capability 数据源: `backend/seed/capabilities/` + DataService Catalog `capabilities`
Capability Skill 数据源: `backend/seed/skills/` + DataService Catalog `capability_skills`

本文件记录当前工作台 capability 目录事实源。Wenjin 已切到 Super Agent Harness mission catalog：旧 workflow-step id 已移除，不提供 alias、fallback 或双读兼容层。

## 1. Canonical Rules

1. capability seed 必须声明 `schema_version: capability.v2`。
2. skill seed 必须声明 `schema_version: capability_skill.v2`。
3. DataService Catalog 是 capability / skill SSOT；loader、admin save、runtime launch 都使用同一套 v2 schema 和 Catalog DataService client，不允许回退到 request DB session。
4. `feature_id` 仅保留为传输字段名，字段值必须是 canonical mission capability id。
5. Prism 是文档编辑/预览主 surface；写作变更进入 Prism review item，不直接覆盖主稿。
6. sandbox 开放边界由 `sandbox_policy` 明确表达；禁止 docker socket、privileged、host network、host paths、sibling container、server control。
7. Sandbox 只允许 agent/runtime 使用，不作为用户 room、console 或公开任意执行 API 暴露；用户只审阅 sandbox traces、artifacts 和 provenance。
8. 多步 capability 必须用分阶段 `depends_on` 串起上游输出；不能把 planner/searcher/writer/reviewer 放进同一个并行 phase。
9. skill prompt 必须包含可执行 operating rules 和 output contract；详细内容设计记录见 `docs/current/capability-skill-content-optimization.md`。
10. `software_copyright` 与 `patent` 默认面向中国用户：软著按中国软著登记材料组织，专利按中国/CNIPA 申请实践组织；PCT/海外规则仅在用户明确指定时启用。

## 2. Workspace Types

- `thesis`
- `sci`
- `proposal`
- `software_copyright`
- `patent`

总计: 5 个 workspace 类型，27 个用户可见 mission capability，15 个 worker skill。`entry_tier: hidden` 的内部诊断 capability 不计入用户目录。

## 3. Mission Capability Matrix

### 3.1 Thesis

| capability id | entry | primary surface | stage |
| --- | --- | --- | --- |
| `idea_to_thesis_manuscript` | Idea 到论文全文 | Prism | structure |
| `thesis_research_pack` | 论文研究包 | Prism | research |
| `thesis_empirical_analysis` | 论文实证分析 | Prism | collection |
| `thesis_revision_pass` | 论文修订 | Prism | writing |
| `thesis_defense_pack` | 答辩材料包 | Prism | review |
| `thesis_reference_curation` | 参考文献整理 | Prism | review |

### 3.2 SCI

| capability id | entry | primary surface | stage |
| --- | --- | --- | --- |
| `research_question_to_paper` | SCI 论文主稿 | Prism | structure |
| `sci_literature_positioning` | SCI 文献定位 | Prism | research |
| `sci_empirical_package` | SCI 实证包 | Prism | collection |
| `sci_revision_for_journal` | SCI 期刊修订 | Prism | review |
| `journal_submission_strategy` | 投稿策略 | Prism | review |
| `response_to_reviewers` | 审稿回复 | Prism | writing |
| `reproducibility_audit` | 可复现性审计 | Prism | collection |

### 3.3 Proposal

| capability id | entry | primary surface | stage |
| --- | --- | --- | --- |
| `idea_to_proposal_package` | 申报书整包 | Prism | structure |
| `proposal_background_pack` | 申报背景包 | Prism | research |
| `technical_route_package` | 技术路线包 | Prism | structure |
| `feasibility_and_risk_review` | 可行性与风险评审 | Prism | review |
| `proposal_polish_for_review` | 申报书送审润色 | Prism | writing |

### 3.4 Software Copyright

| capability id | entry | primary surface | stage |
| --- | --- | --- | --- |
| `software_copyright_application_pack` | 软著申请包 | Prism | structure |
| `software_technical_manual` | 软件技术说明书 | Prism | writing |
| `software_evidence_pack` | 软著证据包 | Prism | collection |
| `software_architecture_diagrams` | 软件架构图 | Prism | writing |

### 3.5 Patent

| capability id | entry | primary surface | stage |
| --- | --- | --- | --- |
| `invention_to_patent_draft` | 专利初稿 | Prism | structure |
| `prior_art_and_novelty_pack` | 现有技术与新颖性包 | Prism | research |
| `claims_strategy` | 权利要求策略 | Prism | structure |
| `embodiment_and_drawings` | 实施例与附图 | Prism | writing |
| `office_action_response` | 审查意见答复 | Prism | writing |

## 4. Worker Skill Catalog

skills 是 worker instruction packs，不再作为用户入口 capability。

- `research-scout`
- `literature-synthesizer`
- `source-quality-auditor`
- `manuscript-architect`
- `evidence-analyst`
- `figure-engineer`
- `manuscript-writer`
- `citation-auditor`
- `review-critic`
- `grant-planner`
- `proposal-writer`
- `patent-strategist`
- `patent-drafter`
- `software-structure-planner`
- `software-doc-drafter`

## 5. Launch And Runtime Truth

1. Chat Agent 根据 DataService preload 的 v2 mission catalog 识别用户意图。
2. `launch_feature` 只接受 `schema_version == "capability.v2"` 的 capability。
3. Lead Agent v2 初始 state 注入 `capability_policy`：`mission`、`context_policy`、`sandbox_policy`、`review_policy`、`quality_gates`。
4. Chat Agent 不注册 sandbox-backed bash/file tools，也不通过 middleware acquire sandbox。
5. Lead Agent graph 中的 subagent 才能按 `sandbox_policy.allowed_operations` 触发 sandbox job；当前内部 Python 自检由 `sandbox_python` subagent 进入 Docker provider。
6. Compute projection 从 `sandbox_policy.mode` 判断 sandbox requirement。
7. Dashboard 和 workspace summary 由 Catalog + Execution history 生成 mission progress，不再维护 per-workflow status builder。
8. ResultCard、CompletedView、chat block、Prism Changes 共享 ReviewItem/ReviewBatch 事实源。

## 6. Change Rules

1. 新 capability 先改 v2 seed/schema，再改 runtime/frontend/docs。
2. 新 skill 先改 v2 skill seed/schema，再接入 mission `graph_template`。
3. 不得新增旧 workflow id、alias map、fallback resolver 或双读兼容层。
4. 任何 sandbox 权限扩大必须写入 `sandbox_policy` 并通过 schema validator。
5. 不得新增用户侧 sandbox console、公开 `sandbox/exec` endpoint 或任意命令执行入口；sandbox job 必须从 agent/runtime 内部链路产生。
6. 文档改动必须同步本文件、`workspace-current-state.md`、`architecture.md`。
