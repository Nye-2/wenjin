# Wenjin Docs

更新时间：2026-06-02
状态：Current

`docs/` 只保留两类内容：

1. `current/`：当前实现的唯一事实源与开发指导文档
2. `superpowers/`：历史计划/设计稿，保留原样；除非 `current/` 明确引用，否则不作为当前实现依据

## 快速入口

- `current/documentation-map.md`：当前文档总导航
- `current/architecture.md`：唯一当前架构总览
- `current/workspace-current-state.md`：workspace / thread / execution / compute 当前行为
- `current/frontend-feature-plugin-contract.md`：前后端 feature / thread / execution 契约
- `current/workspace-feature-catalog.md`：workspace type / capability / skill 当前目录
- `current/workspace-reference-library.md`：Reference Library 与 citation 当前事实源
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
- `docs/superpowers/` 只保留历史设计/计划，不参与当前实现判定
- 历史事实若仍有追溯价值，通过 Git 历史或 `docs/superpowers/` 追溯；不要在 `docs/current/` 放发布说明、handoff 或 review history
- 文档与实现冲突时，以实现为准，并在同一改动中回补 `docs/current/`
