# Workspace Feature Catalog

更新时间: 2026-04-15
数据源: `backend/src/workspace_features/registry.py`
skill 数据源: `backend/src/workspace_features/skills.py`

## 1. Canonical Workspace Types

- `thesis`
- `sci`
- `proposal`
- `software_copyright`
- `patent`

总计: 5 个 workspace 类型，23 个 feature。
附加说明: 当前共有 24 个 chat skills。
补充: `compile_export` 已移除，编译/导出统一走 WenjinPrism（`/latex`）。

## 2. Feature Matrix

### 2.1 Thesis (5)

| feature_id | 名称 | handler_key | task_type | panel | stages |
|---|---|---|---|---|---|
| `deep_research` | 深度调研 | `thesis.deep_research` | `workspace_feature` | `deep_research_panel` | `search/analyze/synthesize` |
| `literature_management` | 文献管理 | `thesis.literature_management` | `workspace_feature` | - | - |
| `opening_research` | 开题调研 | `thesis.opening_research` | `workspace_feature` | `opening_research_panel` | `research/outline/refine` |
| `thesis_writing` | 论文写作 | `thesis.thesis_writing` | `workspace_feature` | `thesis_editor` | `outline/write/revise` |
| `figure_generation` | 图表生成 | `thesis.figure_generation` | `workspace_feature` | `figure_panel` | `analyze/design/generate` |

### 2.2 SCI (8)

| feature_id | 名称 | handler_key | task_type | panel | stages |
|---|---|---|---|---|---|
| `literature_search` | 文献检索 | `sci.literature_search` | `workspace_feature` | `literature_panel` | `search/filter` |
| `paper_analysis` | 论文分析 | `sci.paper_analysis` | `workspace_feature` | `analysis_panel` | `parse/analyze/summarize` |
| `writing` | 论文写作 | `sci.writing` | `workspace_feature` | `editor_panel` | `plan/write/revise` |
| `literature_review` | 文献综述 | `sci.literature_review` | `workspace_feature` | `analysis_panel` | `collect/synthesize/draft` |
| `framework_outline` | 框架与摘要 | `sci.framework_outline` | `workspace_feature` | `editor_panel` | `position/outline/abstract` |
| `figure_generation` | 图表生成 | `sci.figure_generation` | `workspace_feature` | `figure_panel` | `analyze/design/generate` |
| `peer_review` | 同行评审 | `sci.peer_review` | `workspace_feature` | `analysis_panel` | `inspect/score/advise` |
| `journal_recommend` | 期刊推荐 | `sci.journal_recommend` | `workspace_feature` | `analysis_panel` | `profile/match/rank` |

### 2.3 Proposal (4)

| feature_id | 名称 | handler_key | task_type | panel | stages |
|---|---|---|---|---|---|
| `proposal_outline` | 申报书大纲 | `proposal.proposal_outline` | `workspace_feature` | `outline_editor` | `analyze/generate` |
| `background_research` | 背景调研 | `proposal.background_research` | `workspace_feature` | `literature_panel` | `search/summarize` |
| `experiment_design` | 实验设计 | `proposal.experiment_design` | `workspace_feature` | `outline_editor` | `hypothesis/variables/evaluation` |
| `figure_generation` | 图表生成 | `proposal.figure_generation` | `workspace_feature` | `figure_panel` | `analyze/design/generate` |

### 2.4 Software Copyright (3)

| feature_id | 名称 | handler_key | task_type | panel | stages |
|---|---|---|---|---|---|
| `copyright_materials` | 材料准备 | `software_copyright.copyright_materials` | `workspace_feature` | `outline_editor` | `collect/organize/review` |
| `technical_description` | 技术说明 | `software_copyright.technical_description` | `workspace_feature` | `editor_panel` | `analyze/draft/revise` |
| `figure_generation` | 图表生成 | `software_copyright.figure_generation` | `workspace_feature` | `figure_panel` | `analyze/design/generate` |

### 2.5 Patent (3)

| feature_id | 名称 | handler_key | task_type | panel | stages |
|---|---|---|---|---|---|
| `patent_outline` | 专利框架 | `patent.patent_outline` | `workspace_feature` | `outline_editor` | `analyze/structure/refine` |
| `prior_art_search` | 现有技术检索 | `patent.prior_art_search` | `workspace_feature` | `literature_panel` | `search/compare` |
| `figure_generation` | 图表生成 | `patent.figure_generation` | `workspace_feature` | `figure_panel` | `analyze/design/generate` |

## 3. Change Rules

1. 新 feature 必须先改 registry，再改执行链路与前端展示。
2. `feature_id` 与 `handler_key` 视为对外稳定标识，不应随意改名。
3. `task_type`、`panel`、`stages` 变更时，必须同步回归前端路由、任务编排和 workspace feature 文档。

## 4. Entry Skills

skills 是 chat 层的 feature 入口语义。一个 skill 绑定一个 canonical feature，可附带默认参数与 follow-up skill。

### 4.1 Thesis

- `deep-research` -> `deep_research`
- `literature-manager` -> `literature_management`
- `literature-reviewer` -> `opening_research`
- `framework-designer` -> `thesis_writing` (`action=generate_outline`)
- `fullpaper-writer` -> `thesis_writing` (`action=write_all`)
- `figure-designer` -> `figure_generation`

### 4.2 SCI

- `deep-research` -> `literature_search`
- `paper-analyst` -> `paper_analysis`
- `section-writer` -> `writing`
- `literature-reviewer` -> `literature_review`
- `framework-designer` -> `framework_outline`
- `figure-designer` -> `figure_generation`
- `peer-reviewer` -> `peer_review`
- `journal-recommender` -> `journal_recommend`

### 4.3 Proposal

- `proposal-writer` -> `proposal_outline`
- `background-scout` -> `background_research`
- `experiment-designer` -> `experiment_design`
- `figure-designer` -> `figure_generation`

### 4.4 Software Copyright

- `copyright-writer` -> `copyright_materials`
- `tech-doc-writer` -> `technical_description`
- `figure-designer` -> `figure_generation`

### 4.5 Patent

- `patent-drafter` -> `patent_outline`
- `prior-art-scout` -> `prior_art_search`
- `figure-designer` -> `figure_generation`
