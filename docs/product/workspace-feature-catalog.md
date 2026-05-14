# Workspace Feature Catalog

更新时间: 2026-05-14
状态: Current
数据源: `backend/src/workspace_features/registry.py`
运行时画像源: `backend/src/workspace_features/runtime_profiles.py`
技能映射源: `backend/src/services/workspace_skill_labels.py`

本文件记录当前 workspace feature 目录的对外事实源。feature 已完全收敛到 execution-first 架构：

- 稳定标识是 `feature_id`
- 执行主对象是 `ExecutionRecord`
- 启动入口统一通过 chat / `FeatureIngressService`
- 不再存在 `handler_key` / `workspace_feature task` 作为主执行桥

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

| feature_id | 名称 | agent | panel | stages |
| --- | --- | --- | --- | --- |
| `deep_research` | 深度调研 | `scout` | `deep_research_panel` | `search/analyze/synthesize` |
| `literature_management` | 文献管理 | `librarian` | - | - |
| `opening_research` | 开题调研 | `scout` | `opening_research_panel` | `research/outline/refine` |
| `thesis_writing` | 论文写作 | `thesis_writer` | `thesis_editor` | `outline/write/revise` |
| `figure_generation` | 图表生成 | `figure_planner` | `figure_panel` | `analyze/design/generate` |

### 2.2 SCI (8)

| feature_id | 名称 | agent | panel | stages |
| --- | --- | --- | --- | --- |
| `literature_search` | 文献检索 | `scout` | `literature_panel` | `search/filter` |
| `paper_analysis` | 论文分析 | `analyst` | `analysis_panel` | `parse/analyze/summarize` |
| `writing` | 论文写作 | `writer` | `editor_panel` | `plan/write/revise` |
| `literature_review` | 文献综述 | `reviewer` | `analysis_panel` | `collect/synthesize/draft` |
| `framework_outline` | 框架与摘要 | `planner` | `editor_panel` | `position/outline/abstract` |
| `figure_generation` | 图表生成 | `figure_planner` | `figure_panel` | `analyze/design/generate` |
| `peer_review` | 同行评审 | `reviewer` | `analysis_panel` | `inspect/score/advise` |
| `journal_recommend` | 期刊推荐 | `reviewer` | `analysis_panel` | `profile/match/rank` |

### 2.3 Proposal (4)

| feature_id | 名称 | agent | panel | stages |
| --- | --- | --- | --- | --- |
| `proposal_outline` | 申报书大纲 | `planner` | `outline_editor` | `analyze/generate` |
| `background_research` | 背景调研 | `scout` | `literature_panel` | `search/summarize` |
| `experiment_design` | 实验设计 | `planner` | `outline_editor` | `hypothesis/variables/evaluation` |
| `figure_generation` | 图表生成 | `figure_planner` | `figure_panel` | `analyze/design/generate` |

### 2.4 Software Copyright (3)

| feature_id | 名称 | agent | panel | stages |
| --- | --- | --- | --- | --- |
| `copyright_materials` | 材料准备 | `planner` | `outline_editor` | `collect/organize/review` |
| `technical_description` | 技术说明 | `writer` | `editor_panel` | `analyze/draft/revise` |
| `figure_generation` | 图表生成 | `figure_planner` | `figure_panel` | `analyze/design/generate` |

### 2.5 Patent (3)

| feature_id | 名称 | agent | panel | stages |
| --- | --- | --- | --- | --- |
| `patent_outline` | 专利框架 | `planner` | `outline_editor` | `analyze/structure/refine` |
| `prior_art_search` | 现有技术检索 | `scout` | `literature_panel` | `search/compare` |
| `figure_generation` | 图表生成 | `figure_planner` | `figure_panel` | `analyze/design/generate` |

## 3. Launch And Runtime Truth

1. feature 的唯一稳定外部标识是 `feature_id`。
2. 启动与恢复统一走：
   - chat -> `launch_feature`
   - HTTP / UI -> `FeatureIngressService`
3. 两条入口都会创建或复用 `ExecutionRecord`，并最终分发到 `execute_execution(execution_id)`。
4. 缺参、busy、resume、commit、refresh 都围绕 `execution_id` 收敛。
5. `TaskRecord` 仍保留为通用异步基础设施，但不再承担 feature 主执行桥语义。

## 4. Change Rules

1. 新 feature 必须先改 registry，再改 runtime profile、execution graph 和前端展示。
2. `feature_id` 视为对外稳定标识，不应随意改名。
3. `agent`、`panel`、`stages` 变更时，必须同步回归 execution / compute UI 和 workspace skill labels。
4. 不得重新引入 `handler_key`、`workspace_feature task` 或平行 launch orchestrator。

## 5. Entry Skills

skills 是 chat 层的 feature 入口语义。一个 skill 绑定一个 canonical feature，可附带默认参数与 follow-up skill。

### 5.1 Thesis

- `deep-research` -> `deep_research`
- `literature-manager` -> `literature_management`
- `literature-reviewer` -> `opening_research`
- `framework-designer` -> `thesis_writing` (`action=generate_outline`)
- `fullpaper-writer` -> `thesis_writing` (`action=write_all`)
- `figure-designer` -> `figure_generation`

### 5.2 SCI

- `deep-research` -> `literature_search`
- `paper-analyst` -> `paper_analysis`
- `section-writer` -> `writing`
- `literature-reviewer` -> `literature_review`
- `framework-designer` -> `framework_outline`
- `figure-designer` -> `figure_generation`
- `peer-reviewer` -> `peer_review`
- `journal-recommender` -> `journal_recommend`

### 5.3 Proposal

- `proposal-writer` -> `proposal_outline`
- `background-scout` -> `background_research`
- `experiment-designer` -> `experiment_design`
- `figure-designer` -> `figure_generation`

### 5.4 Software Copyright

- `copyright-writer` -> `copyright_materials`
- `tech-doc-writer` -> `technical_description`
- `figure-designer` -> `figure_generation`

### 5.5 Patent

- `patent-drafter` -> `patent_outline`
- `prior-art-scout` -> `prior_art_search`
- `figure-designer` -> `figure_generation`
