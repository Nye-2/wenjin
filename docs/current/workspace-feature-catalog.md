# Workspace Mission Capability Catalog

更新时间: 2026-06-15
状态: Current
Capability 数据源: `backend/seed/capabilities/` + DataService Catalog `capabilities`
Capability Skill 数据源: `backend/seed/skills/` + DataService Catalog `capability_skills`
Agent Template 数据源: `backend/seed/agent_templates/` + DataService Catalog `agent_templates`

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
9. enabled `capability_skill.v2.worker.role_prompt` 必须满足 Prompt Contract v1，包含固定 headings：`Role Boundary:`、`Input Interpretation:`、`Operating Rules:`、`Evidence Rules:`、`Output Contract:`、`Quality Gate Behavior:`、`Failure Handling:`、`Anti-Patterns:`。prompt body 仍是 worker 唯一运行时 prompt 来源；schema/admin/seed lint 只做目录校验，不引入第二套 renderer、prompt manager 或运行时拼装层。
10. `software_copyright` 与 `patent` 默认面向中国用户：软著按中国软著登记材料组织，专利按中国/CNIPA 申请实践组织；PCT/海外规则仅在用户明确指定时启用。
11. 用户可见 capability 必须在 schema/admin 写入时声明 `routing` 合约：`when_to_use`、`not_for`、至少 3 个 positive examples、至少 3 个 negative examples、`minimum_context`、歧义边界和轻量用户引导。每个 required `minimum_context` key 都必须说明需要用户补齐的最小事实。Chat Agent 使用这些 route-card 做 LLM-only 渐进承诺，不维护 embedding index、关键词硬路由或第二套 router service。
12. agent template 的公开 `expert_profile` / persona 文案必须通过 public-safety 校验：不得暴露 internal id、raw tools、raw logs、stdout/stderr、harness refs 或内部调度术语；`persona_prompt` 必须包含 Role Boundary 以及 Evidence/Safety boundary。

## 2. Workspace Types

- `thesis`
- `sci`
- `proposal`
- `software_copyright`
- `patent`

总计: 5 个 workspace 类型，27 个用户可见 mission capability，33 个 worker skill。`entry_tier: hidden` 的内部诊断 capability 不计入用户目录。

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

- `citation-auditor`
- `claim-verifier`
- `document-outline-builder`
- `evidence-analyst`
- `figure-engineer`
- `format-compliance-checker`
- `grant-planner`
- `literature-synthesizer`
- `manuscript-architect`
- `manuscript-writer`
- `method-design`
- `novelty-mapper`
- `patent-drafter`
- `patent-examiner-rules`
- `patent-strategist`
- `proposal-panel-rules`
- `proposal-writer`
- `query-planner`
- `reporting-guideline-checker`
- `reproducibility-auditor`
- `research-scout`
- `review-critic`
- `sci-journal-rules`
- `software-copyright-rules`
- `software-doc-drafter`
- `software-structure-planner`
- `source-quality-auditor`
- `source-screener`
- `structured-summary`
- `style-polisher`
- `table-builder`
- `task-scope-planner`
- `thesis-school-rules`

## 5. Expert Template Catalog

agent templates 是可被 Lead Agent 动态招募进团队的专家席位，不是用户入口 capability。模板画像由 `expert_profile(schema=wenjin.team.expert_profile.v1)` 描述；capability 可通过 `extensions.team_presentation(schema=wenjin.team.presentation.v1)` 做显示层 override，但不能覆盖工具、技能或权限。

当前基础专家模板共 11 个，事实源是 `backend/seed/agent_templates/*.yaml`：

- `research_planner.v1`（Steve）：研究负责人，拆解目标、排布团队和质量门。
- `research_scout.v1`（文献猎手 Nora）：文献/资料线索定位、来源筛选和 metadata 记录。
- `literature_synthesizer.v1`（综述姐 Athena）：综述、主题矩阵、gap 和可引用论断提炼。
- `methodologist.v1`（方法哥 Bayes）：方法设计、实验/评估方案和可行性检查。
- `evidence_analyst.v1`（证据管家 Iris）：证据分析、结论支撑和复现实验摘要。
- `figure_table_engineer.v1`（图表师傅 Vega）：图表、表格和实验呈现设计。
- `document_architect.v1`（结构师 Morgan）：论文/申报/专利/软著材料结构规划。
- `manuscript_writer.v1`（写作编辑 Olivia）：正文写作、改稿和风格统一。
- `citation_auditor.v1`（引用侦探 Sherlock）：引用、BibTeX、来源一致性和引用风险检查。
- `critical_reviewer.v1`（二审哥 Reviewer 2）：审稿式批判、质量门检查和关键风险定位。
- `generalist_assistant.v1`（补位侠 Max）：补位、整理、摘要和低风险衔接任务。

展示约束：

1. `backend/src/contracts/team_presentation.py` 是专家展示合同事实源。
2. `backend/src/contracts/team_expert.py` 只处理运行态 `expert_snapshot` / `expert_preview_item` sanitizer。
3. 前端只能从 hydrated `ExecutionRecord.node_states[*].node_metadata.team === true` 的 `agent_invocation` 节点投影团队成员。
4. 用户默认视图展示专家实名、阶段摘录和预览，不展示 template id、raw tools、raw skills、stdout/stderr 或 harness internal refs。

## 6. Launch And Runtime Truth

1. Chat Agent 根据 DataService preload 的 v2 mission catalog 识别用户意图。
2. Chat Agent prompt 中的可用能力只渲染 bounded `capability_route_card`，不暴露 graph template、raw tool、raw skill、schema id 或触发词列表给用户。
3. Chat Agent 先在 `answer_in_chat`、`ask_clarification`、`offer_choices`、`launch_feature` 四类交互中选择；只有明确多步产出且最小上下文足够时才调用 `launch_feature`。
4. `launch_feature` 只接受 `schema_version == "capability.v2"` 的 capability。
5. Lead Agent v2 初始 state 注入 `capability_policy`：`mission`、`context_policy`、`sandbox_policy`、`review_policy`、`quality_gates`。
6. Chat Agent 不注册 sandbox-backed bash/file tools，也不通过 middleware acquire sandbox。
7. Lead Agent graph 中的 subagent 才能按 `sandbox_policy.allowed_operations` 触发 sandbox job；当前内部 Python 自检由 `sandbox_python` subagent 进入 Docker provider。
8. Compute projection 从 `sandbox_policy.mode` 判断 sandbox requirement。
9. Dashboard 和 workspace summary 由 Catalog + Execution history 生成 mission progress，不再维护 per-workflow status builder。
10. ResultCard、CompletedView、chat block、Prism Changes 共享 ReviewItem/ReviewBatch 事实源。

## 7. Change Rules

1. 新 capability 先改 v2 seed/schema，再改 runtime/frontend/docs。
2. 新 skill 先改 v2 skill seed/schema，再接入 mission `graph_template`。
3. 新专家模板先改 agent template seed/schema，再通过 capability team policy 招募；不要在前端硬编码专家列表。
4. 不得新增旧 workflow id、alias map、fallback resolver 或双读兼容层。
5. 新增或改动用户可见 capability 时必须同步 `routing` 合约；缺少 routing 的 visible capability 不能通过 schema/admin 保存，也不允许进入发布。
6. 任何 sandbox 权限扩大必须写入 `sandbox_policy` 并通过 schema validator。
7. 不得新增用户侧 sandbox console、公开 `sandbox/exec` endpoint 或任意命令执行入口；sandbox job 必须从 agent/runtime 内部链路产生。
8. 文档改动必须同步本文件、`workspace-current-state.md`、`architecture.md`。
