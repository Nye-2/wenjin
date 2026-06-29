# Wenjin Docs

更新时间：2026-06-30
状态：Current

`docs/current/` 是当前实现事实源。问津当前定位是科研工作台，文档围绕 workspace、capability、专家团队、Wenjin Harness、DataService、Prism、Admin 与 Docker Compose 运维维护。

- `current/`：当前实现的唯一事实源与开发指导文档
- `superpowers/`：阶段性执行计划、spec 草稿和工作记录归档；可用于追溯上下文，但不能作为当前事实源引用

历史方案、审计记录和执行过程稿不进入 `docs/current/`。需要判断当前行为时只看 `docs/current/`；需要追溯某次计划时再查 Git 历史或 `docs/superpowers/` 归档。

## 快速入口

- `current/documentation-map.md`：当前文档总导航
- `current/architecture.md`：唯一当前架构总览
- `current/workspace-current-state.md`：workspace / thread / execution / Workbench / Prism 当前行为
- `current/frontend-feature-plugin-contract.md`：前后端 feature / thread / execution 契约
- `current/workspace-feature-catalog.md`：workspace type / capability / skill / expert template 当前目录
- `current/workspace-reference-library.md`：Reference Library 与 citation 当前事实源
- `current/wenjin-research-navigation-uiux.md`：科研工作台 UI/UX 与视觉系统事实源
- `current/deployment-runbook.md`：Docker Compose-only 部署运行手册
- `current/environment-variables.md`：环境变量基线
- `current/release-gate-checklist.md`：发布与回归门禁
- `current/troubleshooting.md`：运行与联调查错入口

## 阅读建议

1. `docs/README.md`
2. `docs/current/documentation-map.md`
3. `docs/current/architecture.md`
4. `docs/current/workspace-current-state.md`
5. `docs/current/frontend-feature-plugin-contract.md`
6. 需要时再看 `docs/current/` 下对应专题

## 治理规则

- 当前实现、当前契约、当前运维说明，只允许保留在 `docs/current/`
- 不再把过程文档、handoff、review history、implementation log 放入 `docs/current/`；长期事实变化只更新事实源文档
- 历史事实若仍有追溯价值，通过 Git 历史追溯；不要在 `docs/current/` 放发布说明、handoff 或 review history
- 文档与实现冲突时，以实现为准，并在同一改动中回补 `docs/current/`
