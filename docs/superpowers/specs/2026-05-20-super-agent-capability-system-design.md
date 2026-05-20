# Super Agent Harness Capability System Design

Date: 2026-05-20
Status: Product Decisions Accepted / Detailed Design Ready
Scope: capability system, skill system, sandbox system, workspace-specific capability portfolios

## 1. Executive Summary

当前 Wenjin 的 capability seed 仍然带有 workflow 时代的结构痕迹：`outline_generate`、`section_write`、`framework_outline`、`proposal_outline` 这类能力把“中间步骤”当成了“用户入口”。这和现在的 Super Agent Harness 不匹配。

Super Agent Harness 下，用户不应该理解或手动串联 workflow。用户提出一个目标，系统负责把目标拆成研究、实验、写作、图表、审阅、回写等内部阶段。

新的核心定义是：

> **Capability 是用户可启动的可交付 mission，不是 workflow step。**

对应地：

- “写论文大纲”不再是默认主能力；它是 `idea_to_manuscript` 内部的结构规划 stage。
- “写某一段”不再是主工作流入口；它是 Prism 内选区改写、局部补写或 full manuscript 生成时的内部 worker stage。
- “绘制图表”仍可以是用户显式能力，但当它服务于论文全文、实证分析或申报书时，也可以作为上层 capability 的 sandbox/artifact stage。
- “跑实验、实证分析、统计检验、画图”不应混入写作 skill；它们属于 sandbox-backed evidence pipeline，并输出可审阅的 artifacts、figures、tables、methods notes。

目标是将 Wenjin 的能力体系重构为：

```text
Workspace Goal
  -> Capability Mission
  -> Lead Agent Plan
  -> Skills as workers
  -> Sandbox jobs when execution is needed
  -> ResultReviewItems / Prism changes
  -> Rooms commit / manuscript apply
```

### 1.1 Accepted Product Decisions

本版文档吸收 2026-05-20 review 后的产品决策：

1. **允许重设 schema**：Capability / Skill / Sandbox / Review contract 可以按新体系重设，但必须有明确版本、严格字段规范、扩展点和校验规则。
2. **旧体系 clean cutover**：新体系搭建完成且 review 通过后，旧 workflow-step capability 直接删除或禁用；运行时不做 alias、fallback、双读、双写或兼容层。
3. **所有 workspace 进入 Prism**：Prism 从“LaTeX manuscript editor”升级为 workspace 的通用文档编辑/预览 surface。Thesis / SCI / Proposal / Patent / Software Copyright 的主文档产出都进入 Prism review。
4. **Sandbox 尽可能开放但语言统一**：Sandbox 的开放程度决定 Super Agent Harness 能力边界。首版统一使用 Python / CLI / 绘图 / 编译 / 数据处理 / 包安装，不引入 R；同时必须禁止干涉宿主机、其他容器、Docker daemon、compose 网络和服务器底层。
5. **Sandbox 网络安全优先**：Sandbox 不承担任意 web browsing。LLM API 侧可以配备 web search / research tools；Sandbox 只在必要时通过受控 allowlist 下载包或读取明确授权的数据源。
6. **数据契约可以做大**：ResultReviewItem、SandboxArtifact、Provenance、PrismChange、CapabilityMission 等契约可以扩展到足够表达长期架构，不为短期省字段牺牲清晰度。
7. **DataService 是后续收敛目标**：允许在合适时机系统性整理数据服务/数据模型，新增 `dataservice` 模块统一 workspace data access、Prism document data、review items、sandbox artifacts、provenance 和 room commit。
8. **Capability 数量以产品合适为准**：不追求固定数量；每个 workspace 控制 primary missions，contextual/utility 能力可隐藏或从 Prism/Rooms 触发。

## 2. Current System Audit

### 2.1 Current Runtime Facts

当前系统已有可复用基础：

- Capability YAML + DB 是执行定义事实源。
- CapabilitySkill YAML + DB 是 subagent instruction pack。
- Chat Agent 负责 intent / required decisions / dispatch。
- Lead Agent v2 将 capability `graph_template` 编译成 LangGraph。
- `TaskReport.outputs` 支持 `library_item`、`document`、`memory_fact`、`decision`、`task`。
- Prism review items 已成为 manuscript file changes 的事实源。
- Sandbox / execution providers 已能承载 LaTeX、Python plot、Mermaid、AI image 等执行能力。
- Workspace rooms 已经提供 Library / Documents / Decisions / Memory / Run History / Sandbox / Tasks / Settings 的数据边界。

### 2.2 Current Mismatch

当前 25 个 seed capability 的主要问题：

1. **入口粒度偏 workflow step**
   - Thesis: `outline_generate`、`section_write`、`section_revise`
   - SCI: `framework_outline`、`section_writing`
   - Proposal: `proposal_outline`
   - Patent: `patent_outline`

2. **能力边界不表达用户真实目标**
   - 用户通常不是“我要大纲”，而是“我有这个 idea，帮我形成完整论文/申报书/专利稿”。
   - 大纲只是系统为了写好全文必须做的内部结构化判断。

3. **实验/数据/图表和写作没有被显式建模**
   - `figure_generation` 现在是独立能力，但没有区分概念图、实证图、实验流程图、专利附图、软著架构图。
   - `experiment_design` 是文本规划，不是 sandbox-backed experimental/evidence pipeline。

4. **Skill 粒度偏“旧 agent 角色名”**
   - `framework-designer`、`section-writer`、`literature-reviewer` 仍像 workflow 节点。
   - 新体系需要 Skill 表示可复用 worker 能力，如 `evidence-analyst`、`manuscript-architect`、`claim-drafter`、`figure-engineer`。

5. **Sandbox 没有进入 capability 设计语言**
   - YAML 里只有 `runtime.requires_sandbox`，但没有表达 sandbox job 的目的、输入、产物、复现实验记录、artifact commit 规则。

## 3. New Concept Model

### 3.1 Capability

Capability 是用户可启动的 mission，必须满足四个条件：

1. **目标可被用户理解**
   - “根据确定 idea 写全文”
   - “基于数据跑实证分析并生成结果图表”
   - “把发明交底书变成专利初稿”

2. **输出可被审阅和回写**
   - Documents room
   - Library room
   - Decisions / Memory candidates
   - Prism pending file changes
   - Sandbox artifacts

3. **内部可以包含多个 stage**
   - research
   - planning
   - sandbox execution
   - writing
   - figure/table generation
   - citation/provenance audit
   - review

4. **由 Lead Agent 运行时裁量**
   - Capability 定义 mission、输入、产物和边界。
   - Lead Agent 决定是否需要调用哪些 skills、是否进入 sandbox、是否先补充上下文。

Capability 不是：

- 单个 prompt
- 单个旧 workflow node
- 单个 UI button 的硬编码 handler
- “大纲/章节/图表”这种天然中间步骤的默认拆分

### 3.2 Skill

Skill 是 subagent instruction pack，不是用户产品入口。

Skill 应该描述：

- worker role
- input contract
- output contract
- allowed tools
- allowed room context
- sandbox access policy
- quality gates

Skill 可以被多个 capability 复用。例如：

| Skill | Role | Used By |
| --- | --- | --- |
| `research-scout` | 建立材料池、检索、筛选、摘要 | thesis / sci / proposal / patent |
| `evidence-analyst` | 在 sandbox 中跑统计、实验、表格、图 | thesis / sci / proposal |
| `manuscript-architect` | 把 idea 和证据转成全文结构策略 | thesis / sci |
| `manuscript-writer` | 生成可进入 Prism review 的正文变更 | thesis / sci |
| `citation-auditor` | 检查 claims 与来源绑定 | thesis / sci / proposal |
| `figure-engineer` | 生成图表规格、Mermaid、绘图脚本、图注 | all workspaces |
| `review-critic` | 审稿、查缺、风险定位 | thesis / sci / proposal |
| `grant-planner` | 申报书目标、路线、可行性拆解 | proposal |
| `patent-claim-drafter` | 权利要求、说明书结构、实施例 | patent |
| `software-doc-drafter` | 软著说明书、模块说明、用户手册 | software_copyright |

### 3.3 Sandbox

Sandbox 是执行基座，不是“一个能力”。

Sandbox 负责：

- 代码执行
- 数据处理
- 统计/实验/仿真
- 图表生成
- LaTeX 编译
- artifact materialization
- reproducibility record

Capability 需要通过 `sandbox_policy` / `SandboxJob` 声明：

| Field | Meaning |
| --- | --- |
| `intent` | 为什么需要 sandbox，例如 empirical_analysis / figure_render / latex_compile |
| `inputs` | 来自 Documents / Library / uploaded files / user brief |
| `allowed_operations` | read_data、run_python、render_figure、compile_latex 等 |
| `expected_artifacts` | tables、figures、logs、notebooks、compiled pdf |
| `review_policy` | 产物是否默认进入 ResultReviewItem |
| `provenance_policy` | artifact 需要关联哪些 input ids、execution id、source hashes |

### 3.4 Result Review

所有 capability 产出必须进入统一 review contract。

当前 `TaskReport.outputs` 支持 room outputs，Prism file changes 已通过 `review_items` 承载。新体系应把 review target 明确分层：

```text
ResultReviewItem
  target_kind:
    - room_document
    - room_library_item
    - room_decision_candidate
    - room_memory_candidate
    - room_task
    - prism_file_change
    - sandbox_artifact
  state:
    - pending
    - applied
    - rejected
    - deferred
    - reverted
```

用户看到的是“这些结果是否接受/写入/应用”，不是底层 output kind。

## 4. Design Principles

### P1. Mission-first, stage-second

对用户暴露 mission，不暴露默认流程步骤。Stage 是 Lead Agent 的内部执行结构，用于 Compute panel 可视化和回放，不是主入口目录。

### P2. Capability owns product promise, Skill owns execution craft

Capability 描述“交付什么”。Skill 描述“谁来做、怎么做、质量标准是什么”。

### P3. Sandbox only enters when the work requires execution

写一段纯文本不需要 sandbox。跑实证、生成图表、编译 LaTeX、复现实验、抽取表格，需要 sandbox。

### P4. Authored document changes go through Prism, not Documents-only

当输出是工作区的主文档正文改动时，进入 Prism pending changes。不要把“完整论文.md”“申报书.md”“专利初稿.md”“软著说明书.md”直接塞进 Documents 后让用户自己复制。

Documents room 保存辅助材料、分析报告、实验记录、生成说明、投稿包和可下载附件。Prism 保存主文档的可编辑内容、预览结果、文件变更和人工审阅状态。

Prism 的产品定位从当前 LaTeX manuscript surface 扩展为：

> **Workspace Document Editor / Previewer**：承载每个 workspace 的 primary authored document，提供编辑、预览、diff review、apply/revert、source provenance、compile/render/export。

不同 workspace 可以使用不同 Prism adapter：

| Workspace | Prism Adapter | Primary Document |
| --- | --- | --- |
| Thesis | LaTeX / Markdown-to-LaTeX | thesis manuscript |
| SCI | LaTeX / Markdown-to-LaTeX | SCI manuscript |
| Proposal | structured Markdown / form sections | proposal package |
| Software Copyright | structured Markdown / document sections | software manual and application material |
| Patent | structured Markdown / claim-description sections | patent draft |

实现上可以先复用现有 Prism route 和 review contract，但 schema 命名不应继续被 `LatexProject` 绑定死；后续应抽象为 workspace primary document / prism project，并用 adapter 表达 LaTeX、Markdown、DOCX/form 等渲染差异。

### P5. Every serious claim needs provenance

全文写作、申报书论证、专利创造性判断都必须记录来源。没有来源的内容可以作为草案，但应在 review UI 中标注低置信。

### P6. User decisions are durable state

题目、研究对象、方法选择、章节结构、术语翻译、投稿期刊、保护段落都应进入 Decisions 或 Memory candidate，经用户确认后进入 workspace context。

### P7. No compatibility capability layer

旧 workflow 能力不保留为并行入口。迁移时直接重命名、合并、禁用旧入口，运行时只认新 mission catalog。

## 5. Target Schema Principles

新体系允许重设 schema，但 schema 必须满足以下规范：

1. **Versioned**：每类 YAML / DB contract 都必须有 `schema_version`，例如 `capability.v2`、`capability_skill.v2`、`result_review.v2`、`sandbox_job.v1`。
2. **Strict by default**：Pydantic model 默认 `extra="forbid"`，禁止拼写错误静默进入运行时。
3. **Explicit extension point**：需要扩展时使用 `extensions: {}` 或 `x_*` 命名空间，不允许把新语义塞进 `notes`。
4. **No runtime fallback**：迁移完成后运行时只读 v2 schema；旧 seed/旧字段不参与 launch。
5. **Schema owns policy**：Capability 不只描述 graph，也必须描述 mission、surface、review target、context access、sandbox policy 和 quality gates。
6. **Contracts are reviewable**：所有写入 workspace 的产物都必须能转为 review item；不能出现 agent 直接写主文档、直接写 Memory/Decisions 的路径。

### 5.1 Capability v2 YAML

建议的 capability v2 结构：

```yaml
schema_version: capability.v2
id: idea_to_thesis_manuscript
workspace_type: thesis
enabled: true

display:
  name: Idea 到论文全文
  description: 根据已确认 idea、材料和格式要求生成或更新完整论文主稿
  icon: file-pen
  color: blue
  order: 10
  entry_tier: primary      # primary | contextual | utility | hidden

intent:
  description: 用户有明确研究 idea，希望生成或更新完整论文主稿
  trigger_phrases:
    - 写全文
    - 根据 idea 写论文
  disambiguation:
    when_user_asks_outline: use_deliverable_structure_only
    when_user_selects_text: prefer_prism_contextual_action

mission:
  goal: produce_or_update_primary_document
  primary_surface: prism
  document_role: primary_manuscript
  user_promise: 生成可审阅、可回滚、带来源追踪的主文档变更
  allowed_deliverables:
    - full_document_update
    - structure_only
    - section_update
    - evidence_pack

inputs:
  required_decisions:
    - key: research_idea
      ask: 你的核心研究 idea 是什么？
      type: string
      persist_as: decision
    - key: degree_level
      ask: 论文层次是本科、硕士还是博士？
      type: string
      persist_as: decision
  brief_schema:
    type: object
    required:
      - research_idea
    properties:
      research_idea:
        type: string
      deliverable:
        type: string
        enum: [full_document_update, structure_only, section_update]

context_policy:
  room_reads:
    library: summary
    documents: excerpts
    decisions: full
    memory: relevant
    tasks: related
  prism_context:
    include_outline: true
    include_target_files: true
    include_protected_sections: true
    include_pending_review_summary: true
    full_text_access: explicit_tool_only

sandbox_policy:
  mode: conditional       # none | optional | conditional | required
  profiles:
    - analysis
    - visualization
    - latex_compile
  allowed_operations:
    - run_python
    - install_python_packages
    - render_figures
    - compile_latex
    - read_workspace_files
    - write_sandbox_outputs
  isolation:
    provider: docker
    network: default_deny_allowlist
    allow_host_docker_socket: false
    allow_privileged: false
    allow_sibling_containers: false
    allow_host_paths: false
  resource_limits:
    cpu: 2
    memory_mb: 4096
    timeout_seconds: 900
    max_output_mb: 512
  artifact_policy:
    review_required: true
    capture_stdout: true
    capture_scripts: true
    capture_input_hashes: true

review_policy:
  default_targets:
    - prism_file_change
    - sandbox_artifact
    - room_decision_candidate
    - room_memory_candidate
    - room_task
  require_user_acceptance: true
  allow_bulk_accept: true

quality_gates:
  - no_direct_primary_document_write
  - provenance_required_for_claims
  - protected_sections_readonly
  - compile_or_preview_required_before_apply

graph_template:
  phases:
    - name: context_assembly
      tasks: []
    - name: planning
      depends_on: [context_assembly]
      tasks: []
```

### 5.2 CapabilitySkill v2 YAML

Skill 不再表示用户入口，而是 worker 能力包：

```yaml
schema_version: capability_skill.v2
id: evidence-analyst
enabled: true
display_name: Evidence Analyst
description: 在 sandbox 中完成数据分析、统计检验、图表和结果说明

worker:
  category: evidence
  subagent_type: sandbox_runner
  role_prompt: |
    You execute reproducible analysis inside the workspace sandbox.

io_contract:
  input_schema:
    type: object
    required:
      - analysis_goal
      - input_artifacts
  output_schema:
    type: object
    required:
      - artifacts
      - methods_note
      - limitations

context_access:
  room_reads:
    documents: excerpts
    decisions: relevant
    memory: relevant
  prism_context: summary

tool_policy:
  allowed_tools:
    - sandbox.run_python
    - sandbox.read_file
    - sandbox.write_file
    - sandbox.render_figure

sandbox_access:
  mode: required
  profiles:
    - analysis
    - visualization

quality_gates:
  - all_artifacts_have_input_hashes
  - all_figures_have_generation_script
  - no_network_unless_allowlisted
```

### 5.3 ResultReviewItem v2 Contract

所有可回写结果统一成 review item：

```yaml
schema_version: result_review.v2
id: review_item_id
workspace_id: workspace_id
execution_id: execution_id
capability_id: idea_to_thesis_manuscript

producer:
  phase: drafting
  task: write_results_section
  skill_id: manuscript-writer

target:
  kind: prism_file_change     # prism_file_change | sandbox_artifact | room_document | room_library_item | room_decision_candidate | room_memory_candidate | room_task
  surface: prism
  logical_key: results_section
  destination:
    prism_project_id: project_id
    path: main.tex
    section_id: results

payload:
  preview_title: Results section update
  preview_text: 更新结果章节并插入统计图表引用
  diff: {}
  data: {}

provenance:
  source_links:
    - kind: library_item
      id: source_id
    - kind: sandbox_artifact
      id: artifact_id
  input_hashes: []
  script_hashes: []

state:
  status: pending            # pending | applied | rejected | deferred | reverted
  applied_at: null
  applied_by: null

actions:
  preview_endpoint: /api/workspaces/{workspace_id}/review-items/{id}
  apply_endpoint: /api/workspaces/{workspace_id}/review-items/{id}/apply
  reject_endpoint: /api/workspaces/{workspace_id}/review-items/{id}/reject
  defer_endpoint: /api/workspaces/{workspace_id}/review-items/{id}/defer
  revert_endpoint: /api/workspaces/{workspace_id}/review-items/{id}/revert

validation:
  requires_compile: true
  requires_signature: true
  protected_section_policy: block_direct_apply
```

### 5.4 SandboxJob v1 Contract

Sandbox job 是能力边界的核心，允许尽可能强，但必须硬隔离：

```yaml
schema_version: sandbox_job.v1
job_id: job_id
workspace_id: workspace_id
execution_id: execution_id

runtime:
  image: wenjin/sandbox-python:latest
  working_dir: /workspace
  timeout_seconds: 900
  cpu: 2
  memory_mb: 4096
  network: default_deny_allowlist

permissions:
  allow_shell: true
  allow_python: true
  allow_r: false
  allow_package_install: true
  allow_latex_compile: true
  allow_mermaid_render: true
  allow_docker_socket: false
  allow_privileged: false
  allow_host_network: false
  allow_host_paths: false
  allow_sibling_container_access: false

mounts:
  workspace_inputs:
    mode: read_only
  sandbox_outputs:
    mode: read_write
  server_root:
    mode: forbidden

network_policy:
  default: deny
  note: LLM/web-search access is provided by controlled agent tools, not by unrestricted sandbox networking.
  allow:
    - pypi.org
    - files.pythonhosted.org
    - registry.npmmirror.com
    - mirrors.tuna.tsinghua.edu.cn
  deny:
    - docker
    - host.docker.internal
    - metadata.google.internal
    - 169.254.169.254
    - local_compose_network

artifact_capture:
  include_patterns:
    - outputs/**
    - figures/**
    - tables/**
    - logs/**
  max_output_mb: 512
  hash_inputs: true
  hash_scripts: true
```

禁止事项是硬约束：

- 不挂载 `/var/run/docker.sock`
- 不使用 privileged container
- 不使用 host network
- 不挂载宿主机任意路径
- 不访问 sibling containers / compose service DNS
- 不读写数据库、Redis、Docker daemon、宿主机密钥
- 不启动长期驻留服务
- 不允许无资源限制的进程、fork bomb、挖矿类 workload
- 不把 sandbox 接入 Wenjin compose 内网；不能解析或访问 `postgres`、`redis`、`gateway`、`worker`、`nginx` 等服务名
- 不通过 sandbox 任意联网做 research；文献检索、网页搜索、LLM API 调用走 agent tool / model gateway 的受控能力

## 6. Target Capability Portfolio

### 6.1 Thesis Workspace

Thesis 的核心是从研究 idea、资料、数据、学校格式要求，收敛到可编译、可审阅、可答辩的主稿。

| Capability ID | Tier | Display Name | Product Promise | Sandbox Policy | Primary Outputs |
| --- | --- | --- | --- | --- | --- |
| `idea_to_thesis_manuscript` | primary | Idea 到论文全文 | 根据已确认 idea、研究范围、材料和格式要求，生成/更新完整 thesis manuscript | conditional | Prism file changes, structure decisions, writing memory candidates |
| `thesis_research_pack` | primary | 论文研究包 | 围绕题目建立文献、理论、研究空白和可用材料包 | optional | Library items, Prism research notes, decisions |
| `thesis_empirical_analysis` | primary | 实证分析与图表 | 基于数据文件跑统计/模型/可视化，生成可写入论文的结果、表格、图 | required | sandbox artifacts, figures, tables, methods notes, Prism changes |
| `thesis_revision_pass` | primary | 论文整体修订 | 按导师意见、查重风险、逻辑一致性或格式要求修订全文 | conditional | Prism file changes, task list, memory candidates |
| `thesis_defense_pack` | contextual | 答辩材料包 | 从定稿论文生成答辩材料、讲稿、问答准备 | optional | Prism presentation/notes document, tasks |
| `thesis_reference_curation` | utility | 参考文献治理 | 清洗、补全、去重、按规范整理参考文献 | optional | library items, Prism bibliography changes |

旧能力迁移：

| Old Capability | New Treatment |
| --- | --- |
| `outline_generate` | merge into `idea_to_thesis_manuscript` as architecture stage |
| `section_write` | hide as internal `manuscript-writer` skill; expose through Prism local rewrite if needed |
| `section_revise` | merge into `thesis_revision_pass` and Prism selection rewrite |
| `opening_research` | merge into `thesis_research_pack` with `deliverable=opening_report` |
| `deep_research` | merge into `thesis_research_pack` |
| `figure_generation` | keep as utility only if user explicitly asks for standalone figure; otherwise stage inside manuscript/analysis |

### 6.2 SCI Workspace

SCI 的核心是从 research question、evidence、target journal，收敛到论文稿、图表、投稿策略和审稿响应。

| Capability ID | Tier | Display Name | Product Promise | Sandbox Policy | Primary Outputs |
| --- | --- | --- | --- | --- | --- |
| `research_question_to_paper` | primary | 问题到 SCI 初稿 | 根据 research question、材料和目标期刊生成/更新 SCI manuscript | conditional | Prism changes, abstract, title candidates, decisions |
| `sci_literature_positioning` | primary | 文献定位与创新点 | 建立相关工作、gap、contribution positioning | optional | library items, Prism literature notes, decisions |
| `sci_empirical_package` | primary | 实验/实证结果包 | 跑数据分析、实验对比、消融、统计检验和图表 | required | sandbox artifacts, figures, result tables, Prism methods/results changes |
| `sci_revision_for_journal` | primary | 期刊导向修订 | 按目标期刊、审稿风险、语言风格修订稿件 | conditional | Prism changes, reviewer risk report |
| `journal_submission_strategy` | contextual | 投稿策略 | 根据论文画像推荐期刊、改稿策略、投稿顺序 | none | Prism submission strategy document, decisions, tasks |
| `response_to_reviewers` | contextual | 审稿意见回复 | 将 reviewer comments 转为逐条回复和稿件修订建议 | conditional | Prism response letter, Prism changes, task list |
| `reproducibility_audit` | utility | 可复现性检查 | 检查数据、代码、图表、方法描述是否可复现 | required | Prism audit report, tasks, artifact issues |

旧能力迁移：

| Old Capability | New Treatment |
| --- | --- |
| `framework_outline` | internal stage in `research_question_to_paper` |
| `section_writing` | internal writer skill / Prism local rewrite |
| `literature_search` | merge into `sci_literature_positioning` |
| `literature_review` | output mode of `sci_literature_positioning` |
| `paper_analysis` | keep as material-level utility, or move under Library item deep analysis |
| `peer_review` | merge into `sci_revision_for_journal` as review pass |
| `figure_generation` | stage in `sci_empirical_package` or standalone utility |

### 6.3 Proposal Workspace

Proposal 的核心是从项目 idea 和申报指南，收敛到背景、目标、路线、可行性、预算/进度、风险的一整套申报文本。

| Capability ID | Tier | Display Name | Product Promise | Sandbox Policy | Primary Outputs |
| --- | --- | --- | --- | --- | --- |
| `idea_to_proposal_package` | primary | Idea 到申报书 | 根据项目 idea、指南和团队条件生成/更新申报书主稿 | conditional | Prism proposal changes, decisions |
| `proposal_background_pack` | primary | 背景与意义论证 | 检索政策/文献/行业材料，生成背景、意义、现状与痛点 | optional | library items, Prism background notes |
| `technical_route_package` | primary | 技术路线与实验方案 | 设计技术路线、实验验证、评价指标和里程碑 | conditional | Prism route sections, figure specs, tasks |
| `feasibility_and_risk_review` | contextual | 可行性与风险审查 | 审查创新性、可行性、资源匹配和风险缓释 | optional | Prism review report, decisions, tasks |
| `proposal_polish_for_review` | primary | 评审导向润色 | 按申报类型和评审标准压实表达、突出亮点 | optional | Prism changes, reviewer checklist |

旧能力迁移：

| Old Capability | New Treatment |
| --- | --- |
| `proposal_outline` | internal architecture stage in `idea_to_proposal_package` |
| `background_research` | merge into `proposal_background_pack` |
| `experiment_design` | expand into `technical_route_package` |
| `figure_generation` | utility/stage for route diagrams and mechanism figures |

### 6.4 Software Copyright Workspace

Software Copyright 的核心是从软件说明、代码/截图/模块信息，收敛到可提交的软著材料。

| Capability ID | Tier | Display Name | Product Promise | Sandbox Policy | Primary Outputs |
| --- | --- | --- | --- | --- | --- |
| `software_copyright_application_pack` | primary | 软著申请材料包 | 生成申请表填报素材、软件说明、功能模块、材料清单 | optional | Prism application package, decisions, tasks |
| `software_technical_manual` | primary | 技术说明与用户手册 | 生成软件设计说明、操作说明、功能流程、模块说明 | conditional | Prism manual changes, diagrams |
| `software_evidence_pack` | contextual | 代码与界面证据整理 | 整理代码片段、截图说明、版本信息和材料一致性 | conditional | Prism evidence package, sandbox artifacts |
| `software_architecture_diagrams` | utility | 软著架构图 | 生成模块图、流程图、部署图、功能关系图 | required | figures, diagram specs, Prism figure changes |

旧能力迁移：

| Old Capability | New Treatment |
| --- | --- |
| `copyright_materials` | expand into `software_copyright_application_pack` |
| `technical_description` | merge into `software_technical_manual` |
| `figure_generation` | merge into `software_architecture_diagrams` |

### 6.5 Patent Workspace

Patent 的核心是从 invention disclosure 和现有技术，收敛到权利要求、说明书、附图和审查风险。

| Capability ID | Tier | Display Name | Product Promise | Sandbox Policy | Primary Outputs |
| --- | --- | --- | --- | --- | --- |
| `invention_to_patent_draft` | primary | 交底书到专利初稿 | 从发明点、实施方式和现有技术生成专利说明书与权利要求初稿 | optional | Prism patent draft, decisions |
| `prior_art_and_novelty_pack` | primary | 现有技术与新颖性 | 检索现有技术，形成区别特征、风险和规避建议 | optional | library items, Prism novelty report |
| `claims_strategy` | primary | 权利要求策略 | 设计独权/从权层级、保护范围和备选方案 | none | Prism claim set, decisions |
| `embodiment_and_drawings` | contextual | 实施例与附图 | 生成实施例结构、流程图、装置图、附图说明 | required | figures, Prism embodiment/drawing changes |
| `office_action_response` | contextual | 审查意见答复 | 将审查意见转为答复策略、修改建议和对比说明 | optional | Prism response document, tasks |

旧能力迁移：

| Old Capability | New Treatment |
| --- | --- |
| `patent_outline` | internal architecture stage in `invention_to_patent_draft` |
| `prior_art_search` | expand into `prior_art_and_novelty_pack` |
| `figure_generation` | merge into `embodiment_and_drawings` |

## 7. Capability Anatomy

每个新 capability 应由以下层次构成：

```yaml
id: idea_to_thesis_manuscript
workspace_type: thesis
display_name: Idea 到论文全文
intent_description: 用户有明确研究 idea，希望生成或更新完整论文主稿
required_decisions:
  - research_idea
  - degree_level
  - discipline
  - manuscript_target
runtime:
  mode: compute_agentic
mission:
  goal: produce_or_update_primary_manuscript
  primary_surface: prism
  review_targets:
    - prism_file_change
    - decision_candidate
    - memory_candidate
    - sandbox_artifact
stages:
  - context_assembly
  - manuscript_architecture
  - evidence_or_analysis
  - drafting
  - citation_audit
  - review_packaging
skills:
  - research-scout
  - manuscript-architect
  - evidence-analyst
  - figure-engineer
  - manuscript-writer
  - citation-auditor
  - review-critic
```

当前 schema 尚无 `mission` / `context_policy` / `sandbox_policy` / `review_policy` / `quality_gates` 顶层字段。新体系允许直接做 v2 schema migration：

- `graph_template.phases` 继续表示 executable stages。
- `graph_template.tasks[].skill_id` 继续表示 worker skills。
- `mission` 表示产品承诺、primary surface、document role。
- `context_policy` 表示 rooms / Prism / full-text access 边界。
- `sandbox_policy` 替代 boolean `runtime.requires_sandbox`。
- `review_policy` 表示输出 target 与接受规则。
- `quality_gates` 表示运行时必须满足的安全和质量约束。

迁移完成后，旧 `runtime.requires_sandbox` 可以删除；运行时不再消费 boolean fallback。

## 8. Skill System Design

### 8.1 Skill Categories

| Category | Skills |
| --- | --- |
| Research | `research-scout`, `literature-synthesizer`, `source-quality-auditor`, `prior-art-scout` |
| Planning | `manuscript-architect`, `grant-planner`, `patent-strategist`, `software-structure-planner` |
| Evidence | `evidence-analyst`, `experiment-runner`, `statistics-reviewer`, `reproducibility-auditor` |
| Writing | `manuscript-writer`, `proposal-writer`, `patent-drafter`, `software-doc-drafter` |
| Figure | `figure-engineer`, `table-builder`, `diagram-renderer`, `caption-writer` |
| Review | `review-critic`, `citation-auditor`, `format-auditor`, `submission-auditor` |

### 8.2 Skill Contract

每个 skill 应声明：

- `id`
- `display_name`
- `subagent_type`
- `prompt`
- `input_schema`
- `output_schema`
- `allowed_tools`
- `room_context`
- `sandbox_access`
- `quality_gates`

旧 `CapabilitySkillYamlModel` 只有 prompt/tools/resources/config。新体系不继续把结构化语义塞进 `config`；直接新增 `CapabilitySkillYamlV2Model`：

```yaml
schema_version: capability_skill.v2
id: manuscript-writer
enabled: true
display_name: Manuscript Writer
description: 生成可进入 Prism review 的主文档正文变更
worker:
  category: writing
  subagent_type: writer
  role_prompt: |
    You propose document changes. Never write the primary document directly.
io_contract:
  input_schema:
    type: object
    required:
      - document_goal
      - prism_context
  output_schema:
    type: object
    required:
      - proposed_changes
      - provenance_notes
context_access:
  room_reads:
    library: summary
    documents: excerpts
    decisions: full
    memory: relevant
  prism_context: lightweight
tool_policy:
  allowed_tools:
    - prism.read_context
    - review.create_item
sandbox_access:
  mode: none
quality_gates:
  - provenance_required_for_claims
  - no_direct_primary_document_write
```

### 8.3 Subagent Types

当前 registry 只有：

- `react`
- `searcher`

短期可以继续用 `react` 承载多数 skill，但这会让 sandbox、writer、reviewer 的行为边界不够强。中期建议新增 subagent types：

| Subagent Type | Responsibility |
| --- | --- |
| `researcher` | source search, filtering, synthesis |
| `planner` | architecture / route / claim strategy |
| `sandbox_runner` | structured sandbox job execution |
| `writer` | manuscript/proposal/patent/software text generation |
| `reviewer` | critique, risk, audit |
| `artifact_builder` | figures, tables, diagrams |

## 9. Sandbox System Design

### 9.1 Sandbox Modes

| Mode | Typical Use | Outputs |
| --- | --- | --- |
| `none` | pure research/writing/review | documents, decisions |
| `analysis` | empirical data analysis, statistics, model evaluation | tables, logs, notebooks, figures |
| `visualization` | chart rendering, diagram rendering | png/svg/pdf, figure specs |
| `latex_compile` | manuscript compile and format check | pdf, compile logs, error reports |
| `package_build` | software evidence extraction, folder inventory | reports, file manifests |

### 9.2 Sandbox Artifact Contract

Sandbox artifact 应包含：

- artifact id
- execution id
- producing capability id
- producing task id
- input file ids / hashes
- command or script hash
- output path
- mime type
- preview metadata
- reproducibility notes

Artifact 不应自动进入 Documents。它先进入 review item，用户接受后再 commit。

### 9.3 Example: Empirical Analysis Inside Primary Document Generation

```text
idea_to_thesis_manuscript
  context_assembly
    -> read Library / Documents / Decisions / Memory / Prism projection
  manuscript_architecture
    -> create structure decision candidates
  evidence_plan
    -> detect uploaded dataset and required statistical analysis
  sandbox_analysis
    -> run Python scripts
    -> produce tables, plots, analysis log
  drafting
    -> write results/methods/discussion using artifacts
    -> create Prism pending changes
  audit
    -> citation/provenance check
    -> result review packaging
```

用户启动的是“根据 idea 写全文”，不是“先大纲、再实验、再画图、再写结果”的多按钮流程。

## 10. Review And Workspace Commit Model

### 10.1 Target Review Items

| Producer | Review Item Target | Apply Destination |
| --- | --- | --- |
| research skill | `room_library_item` | Library |
| research synthesizer | `room_document` | Documents |
| planning skill | `room_decision_candidate` | Decisions |
| user preference inference | `room_memory_candidate` | Memory |
| sandbox runner | `sandbox_artifact` | Sandbox / Documents after accept |
| writer | `prism_file_change` | Prism primary document files |
| reviewer | `room_task` | Tasks |

### 10.2 Full Document Output

“全文/主文档写作”不应输出一个不可追踪的大文档。它应输出：

- Prism file changes per target file / logical section
- document architecture decisions
- citation/provenance links
- sandbox artifacts used by methods/results
- unresolved tasks for missing evidence or risky claims

## 11. DataService Convergence

新体系会扩大数据模型：Prism universal documents、review item v2、sandbox artifacts、provenance links、capability mission schema、room commits 都会同时出现。为避免服务层继续分散在 `rooms/*`、`prism_*`、`execution_*`、`workspace_*` 中，后续应新增 `dataservice` 模块做一次系统收敛。

DataService 的产品目的不是“再包一层 service”，而是把 Wenjin 的数据边界收敛成一个可治理的后端子系统：

- 数据表和领域模型有明确归属。
- 所有数据库读写通过 repository / domain service 进入。
- Agent、router、Compute、Prism、commit flow 不再到处 import ORM model 或直接 `session.execute`。
- Workspace-scoped 数据访问默认带 `workspace_id` / `user_id` 边界。
- Review / apply / provenance / artifact materialization 使用同一套状态机和审计规则。

目标：

```text
backend/src/dataservice/
  contracts/
  models/
  repositories/
  services/
  projections/
  migrations/
  guards/
```

DataService 的职责：

1. 提供 workspace-scoped data access facade，统一读 Library / Documents / Decisions / Memory / Tasks / Run History / Prism / Sandbox。
2. 提供 Prism universal document repository，不再让业务直接依赖 `LatexProject`；新增 `PrismProject` / `PrismDocument` / `PrismFile` 作为主模型，现有 workspace-owned LaTeX 项目一次性迁移进去。
3. 提供 ResultReviewItem v2 repository 和 state machine。
4. 提供 SandboxArtifact repository，管理 artifact metadata、input hash、script hash、output path 和 preview metadata。
5. 提供 ProvenanceService，统一 source links、artifact links、execution links、document section links。
6. 提供 CommitService v2，将 review item apply 路由到 Prism / rooms / sandbox artifact materialization。
7. 提供 projection builders，给 Chat Agent、Lead Agent、Prism context rail、Compute panel 读取轻量上下文。

### 11.1 Ownership Rules

收敛完成后的规则：

| Layer | Allowed To Import ORM Models | Allowed To Execute SQLAlchemy Queries | Responsibility |
| --- | --- | --- | --- |
| `backend/src/database` | infrastructure only | session / engine only | Base, engine, session, migration bootstrap |
| `backend/src/dataservice/models` | yes | no direct business logic | SQLAlchemy table definitions |
| `backend/src/dataservice/repositories` | yes | yes | query/write one aggregate boundary |
| `backend/src/dataservice/services` | no direct table queries outside repositories | through repositories only | workspace data use cases and state machines |
| `backend/src/dataservice/projections` | through repositories only | through repositories only | read models for agents/UI/Compute |
| routers / agents / compute / execution | no | no | call DataService facade or domain services |

`backend/src/database/models` 在迁移完成后不再新增业务模型。新的业务表直接放入 `backend/src/dataservice/models`。旧模型按领域切片迁移；迁移某个领域时，同一提交内更新 imports 和 tests，不保留运行时双模型。

### 11.2 Initial Data Domains

第一轮 DataService 不一次性搬完整个系统，而是围绕 Super Agent Harness 闭环建立核心数据域：

| Domain | Models | Repository | Domain Service | First Consumers |
| --- | --- | --- | --- | --- |
| Workspace Core | `Workspace`, `WorkspaceSettings` | `WorkspaceRepository` | `WorkspaceDataService` | routers, middleware |
| Rooms | `LibraryItem`, `DocumentV2`, `Decision`, `MemoryFact`, `WorkspaceTask`, `RunHistory`, `Sandbox` | `RoomRepository` split by room | `WorkspaceRoomService` | commit, context assembly |
| Prism Universal Document | `PrismProject`, `PrismDocument`, `PrismFile`, `PrismRender` | `PrismDocumentRepository` | `PrismDocumentService` | Prism route, writer stage |
| Review Item v2 | `ReviewItem`, `ReviewActionLog` | `ReviewItemRepository` | `ReviewWorkflowService` | ResultCard, Prism review |
| Sandbox Artifacts | `SandboxJobRecord`, `SandboxArtifact` | `SandboxArtifactRepository` | `SandboxArtifactService` | sandbox runner, review |
| Provenance | `ProvenanceLink`, `SourceAnchor` | `ProvenanceRepository` | `ProvenanceService` | writer, auditor, Prism context |
| Capability Catalog | `Capability`, `CapabilitySkill` | `CapabilityRepository`, `SkillRepository` | `CapabilityCatalogService` | Chat Agent, admin |

### 11.3 Canonical Access Patterns

DataService 提供三种入口，不混用：

1. **Repository**：最小数据库读写单元。只表达表和 aggregate 的 CRUD / query，不做产品流程。
2. **Domain service**：表达业务动作，例如 `apply_review_item`、`create_prism_document_change`、`record_sandbox_artifact`。
3. **Projection builder**：表达 read model，例如 workspace context projection、Prism surface projection、Compute launch projection。

禁止模式：

- Router 直接 `select(Model)`。
- Agent runtime 直接打开 DB session 查询业务表。
- Commit flow 手写多个 room service 并各自 commit，导致部分成功。
- Prism service 同时承担文件读写、review 状态机、workspace projection 和 provenance 查询。
- Sandbox runner 直接写 Documents；必须先写 SandboxArtifact + ReviewItem。

### 11.4 Transaction And Review Rules

DataService 的事务策略：

1. 一个用户可见 apply/commit 动作对应一个 transaction boundary。
2. `ReviewItem` 状态变更和目标写入必须同事务完成。
3. `RunHistory` / activity / audit event 可以在事务后发布，但必须引用已提交的 state transition id。
4. Sandbox artifacts 默认不可直接 materialize 到 Documents；必须由 `ReviewWorkflowService.apply()` 驱动。
5. Prism primary document 只接受 review item apply 或用户编辑写入，不接受 agent 直接覆盖。

### 11.5 Migration Strategy For Existing Services

现有代码迁移采用“领域切片直接收敛”，不做长期兼容层：

1. **Rooms first**：把 `services/rooms/*` 的读写语义搬入 `dataservice/repositories/rooms.py` 和 `dataservice/services/workspace_rooms.py`。
2. **Review unification**：用 `ReviewItem v2` 统一 `prism_review_items` 与 `TaskReport.outputs` 的可审阅产物。
3. **Prism universal document**：新增 `PrismProject` / `PrismDocument` / `PrismFile`，一次性迁移 workspace-owned `LatexProject` 绑定，不扩展 `LatexProject` 为通用模型。
4. **Commit service v2**：替换 `ExecutionCommitService` 的多 room service 拼装，统一走 `ReviewWorkflowService.apply_many()`。
5. **Projection cleanup**：`WorkspacePrismService`、`workspace_summary_service`、`compute/projection_service` 改为读取 DataService projection。
6. **Import guard**：新增架构测试，禁止新增非 DataService 层直接 import `src.database.models.*` 或直接执行 workspace-scoped query。

### 11.6 First Development Boundary

第一阶段只准备 DataService 开发，不直接改用户链路：

- 新增 `backend/src/dataservice/` 包结构。
- 新增 contracts 和 repository interface。
- 新增 architecture tests，锁定“新数据库访问必须走 DataService”的规则。
- 新增 DataService planning doc，明确模型搬迁顺序。
- 暂不移动旧模型，避免在 schema v2 / Prism universal document 之前制造大范围 import churn。

第二阶段开始实现时，第一批真正落地的代码应是：

- `dataservice/models/review.py`
- `dataservice/models/prism_document.py`
- `dataservice/models/sandbox_artifact.py`
- `dataservice/models/provenance.py`
- `dataservice/repositories/review_items.py`
- `dataservice/repositories/prism_documents.py`
- `dataservice/services/review_workflow.py`

DataService 不负责：

- 直接调用 LLM
- 运行 subagent
- 执行 sandbox job
- 渲染前端 UI
- 绕过 review contract 直接写用户主文档

建议实施时机：

1. 先实现 schema v2、Prism universal document tables 和最小 service adapter，避免过早大迁移阻塞 capability cutover。
2. 当 Prism universal document、review item v2、sandbox artifact 三块都落地后，启动 DataService 收敛任务。
3. 收敛完成后，旧 `services/rooms/*`、`prism_*`、`execution_commit_service` 中的数据访问逻辑逐步迁到 `dataservice`，外部只保留薄 facade。

## 12. UI / UX Implications

### 12.1 Capability Entry Catalog

Workbench 的 capability entry 不应展示 20 多个 workflow 小按钮。每个 workspace 只展示 4-7 个 mission cards。

推荐结构：

- Primary missions: full manuscript / proposal / patent / software pack
- Research/evidence missions
- Revision/review missions
- Utility missions hidden under “More” or triggered contextually from Prism/Rooms

### 12.2 Prism Contextual Actions

局部写作类操作应从 Prism context 出发：

- 改写选区
- 补写本节
- 增补引用
- 解释这段来源
- 保护该段
- 基于审稿意见修改当前 section

这些不一定是 workspace capability catalog 的主入口。它们可以共享同一底层 capability，但 UI entry 是 contextual action。

### 12.3 Compute Panel

Compute panel 展示 capability 内部 stages，而不是旧 workflow 产品模型。用户看到：

- Context assembly
- Evidence analysis
- Drafting
- Review packaging

这解释系统正在做什么，但不要求用户手动管理每个阶段。

## 13. Migration Strategy

### Phase 1: Taxonomy Cut

1. 冻结新 capability IDs。
2. 将旧 seed capability 映射到新 mission catalog，作为迁移 review 表，不作为运行时 alias。
3. 新体系 review 通过后，删除或禁用旧 workflow-step capability seed。
4. 更新 `workspace-feature-catalog.md` 为新入口事实源。

### Phase 2: Skill Refactor

1. 新增 shared core skills。
2. 将旧 `framework-designer`、`section-writer` 等 prompt 拆为更明确的 worker skills。
3. 新增 `CapabilitySkillYamlV2Model`，把 input/output schema、room context、sandbox access、quality gates 升为一等字段，不再塞进通用 `config`。

### Phase 3: Sandbox Harness

1. 定义 sandbox job spec。
2. 新增 `sandbox_runner` subagent type，不用 `react` 临时代替执行边界。
3. 让 sandbox artifacts 进入 review item。
4. 将 empirical/figure/compile artifacts 绑定 execution provenance。
5. 加硬隔离：禁止 Docker socket、privileged、host network、host paths、sibling container access。

### Phase 4: Review Contract Expansion

1. 将 `sandbox_artifact`、`decision_candidate`、`memory_candidate`、`prism_file_change` 统一表达为 review targets。
2. ResultCard / CompletedView / Prism Changes 共享相同状态机。
3. Commit/apply 后写 activity 和 Run History。

### Phase 5: Workspace-Specific Seeds

按 workspace 重写 seed：

- Thesis: 6 mission capabilities
- SCI: 7 mission capabilities
- Proposal: 5 mission capabilities
- Software Copyright: 4 mission capabilities
- Patent: 5 mission capabilities

首版可以保留 27 个 mission-level capability，但 UI 默认只展示每个 workspace 的 4-5 个 primary missions。

## 14. Proposed First Implementation Slice

第一刀直接搭新体系骨架，不保留旧 workflow 运行路径：

1. 新增 schema v2：
   - Capability v2: `display` / `intent` / `mission` / `inputs` / `context_policy` / `sandbox_policy` / `review_policy` / `quality_gates` / `graph_template`
   - CapabilitySkill v2: `worker` / `io_contract` / `context_access` / `tool_policy` / `sandbox_access` / `quality_gates`
   - ResultReviewItem v2: `producer` / `target` / `payload` / `provenance` / `state` / `actions` / `validation`
   - SandboxJob v1: `runtime` / `permissions` / `mounts` / `network_policy` / `artifact_capture`

2. 建立 Prism universal document surface：
   - 所有 workspace primary document 都进入 Prism。
   - 当前 LaTeX Prism 作为 adapter 之一，不再作为 schema 命名中心。
   - 新增 `PrismProject` / `PrismDocument` / `PrismFile`，不继续扩展 `LatexProject` 作为通用模型。
   - Proposal / Patent / Software Copyright 先用 structured Markdown adapter。

3. 实现 sandbox runner 最小闭环：
   - Python / shell / package install / figure render / LaTeX compile。
   - 不引入 R；统计和数据处理统一走 Python。
   - Docker 隔离 + resource limits + default-deny network + package/source allowlist。
   - sandbox artifacts 进入 review item，不直接写 Documents。

4. 重写 capability catalog：
   - Thesis: `idea_to_thesis_manuscript`、`thesis_research_pack`、`thesis_empirical_analysis`、`thesis_revision_pass`
   - SCI: `research_question_to_paper`、`sci_literature_positioning`、`sci_empirical_package`、`sci_revision_for_journal`
   - Proposal: `idea_to_proposal_package`、`proposal_background_pack`、`technical_route_package`
   - Software Copyright: `software_copyright_application_pack`、`software_technical_manual`
   - Patent: `invention_to_patent_draft`、`prior_art_and_novelty_pack`、`claims_strategy`

5. 更新 Chat Agent capability prompt：
   - 让 Chat Agent 选择 mission，不选择 workflow step
   - 对“写大纲”类请求，判断为 `idea_to_*` 的结构规划 intent，而不是独立旧 capability

6. 更新前端 catalog：
   - Workbench 展示 mission cards
   - workflow-step actions 移入 Prism contextual actions 或隐藏入口

7. 回归链路：
   - launch capability
   - Compute graph event
   - TaskReport outputs
   - ResultCard review
   - Prism changes / room commit

## 15. Implementation Decisions

产品决策已收敛，实施采用以下默认方案：

1. Prism universal document surface 新增 `PrismProject` / `PrismDocument` / `PrismFile`，不继续把 `LatexProject` 扩成通用模型；现有 workspace-owned LaTeX primary manuscript 一次性迁移。
2. Sandbox runner 首版使用一个 Python 大镜像，包含 Python、常用科学计算/绘图库、LaTeX compile、Mermaid/diagram render 所需依赖；稳定后再按 workload 拆分镜像。
3. Review item v2 使用通用 review table 作为父表，Prism change / room item / sandbox artifact 是 target-specific payload。
4. Network allowlist 只允许包管理和明确数据源；research / web search / LLM API 走 agent tools，不走 sandbox 任意联网。
5. 旧 capability seed 删除 gate：v2 seeds + schema validation + launch e2e + review/apply e2e 全绿后删除旧 seed。

## 16. Decision Summary

建议采纳以下方向：

1. Capability 从 workflow step 改为 mission。
2. Skill 从 UI 入口改为 worker instruction pack。
3. Sandbox 从“是否需要”布尔值升级为 execution/artifact/provenance contract。
4. 每个 workspace 建 4-7 个 mission-level primary capabilities。
5. 大纲、章节、局部改写、图表等保留为内部 stage 或 contextual actions。
6. 所有 workspace primary authored document 都进入 Prism pending changes，用户审阅后写入主文档。
7. 实证/实验/图表进入 sandbox-backed evidence pipeline，再被写作 stage 使用。
8. 旧 capability 体系在新体系 review 通过后 clean cutover 删除，不做运行时兼容层。
9. Sandbox 首版统一 Python，不引入 R；LLM/Web Search 走受控 agent tools。
10. DataService 作为后续数据模型/数据服务收敛模块，承接 Prism、review、sandbox artifact、provenance、room commit 的统一访问。
