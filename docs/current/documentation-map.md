# Wenjin Current Docs Map

更新时间：2026-06-13
状态：Current

本目录是 Wenjin 当前实现的唯一事实源目录。后续开发、联调、review、发布前检查，优先只看这里。

## 1. 核心入口

| 文档 | 用途 |
| --- | --- |
| `architecture.md` | 唯一当前架构总览；execution-first 主链、边界、开发约束 |
| `workspace-current-state.md` | workspace / thread / execution / compute / ResultCard 当前行为 |
| `frontend-feature-plugin-contract.md` | capability entry / thread / execution 契约 |
| `workspace-feature-catalog.md` | workspace type / capability entry / skill / expert template 当前目录 |
| `workspace-reference-library.md` | Reference Library 当前事实源 |
| `wenjin-research-navigation-uiux.md` | 当前 UIUX / 视觉系统事实源；System-Grade Research Workbench 与 2026-06-05 full-shell migration 基准 |
| `release-gate-checklist.md` | 发布与回归门禁 |

## 2. 运维与环境

| 文档 | 用途 |
| --- | --- |
| `deployment-runbook.md` | 本地与 Compose 部署运行手册 |
| `environment-variables.md` | 环境变量基线 |
| `troubleshooting.md` | 常见问题排查 |

## 3. 文档治理

- 本目录只保存当前事实源。
- 历史 spec / plan / implementation record / audit log 不在 docs 树中长期保留；需要追溯时查 Git 历史。
- 不新增平行架构文档。发现事实源冲突时，优先更新本目录中已有的最小相关文档。

## 4. 推荐阅读顺序

1. `docs/README.md`
2. `docs/current/documentation-map.md`
3. `docs/current/architecture.md`
4. `docs/current/workspace-current-state.md`
5. `docs/current/frontend-feature-plugin-contract.md`
6. 需要时再看对应专题

## 5. 提交前维护清单

1. 改 execution / task / compute / thread 边界：更新 `architecture.md`
2. 改 workspace / thread / ResultCard / refresh / 恢复行为：更新 `workspace-current-state.md`
3. 改 capability entry / thread / execution 公共契约：更新 `frontend-feature-plugin-contract.md`
4. 改 native harness、TeamKernel 工具执行、安全边界或外部 runtime 取舍：更新 `architecture.md` 与 `release-gate-checklist.md`
5. 改 capability / skill / agent template 目录、Prompt Contract v1、routing-depth、expert template public-safety 或 canonical capability entry/routing contract：更新 `workspace-feature-catalog.md` 与 `architecture.md`
6. 改 references / evidence / bibtex / usage trace：更新 `workspace-reference-library.md`
7. 改 workspace-owned Prism route、review item、source link、protected section、agent manuscript context：更新 `workspace-current-state.md`、`architecture.md`、`frontend-feature-plugin-contract.md`
8. 改部署、端口、环境变量、排障：更新 `deployment-runbook.md`、`environment-variables.md`、`troubleshooting.md`
9. 改发布验收口径：更新 `release-gate-checklist.md`
10. 改 Chat run stream、`tool_invocation`/`tool_result`、RunView、Runs drawer、LiveWorkflowPanel：同步更新 `architecture.md`、`workspace-current-state.md`、`frontend-feature-plugin-contract.md`、`release-gate-checklist.md`
11. 改 admin dashboard、模型目录、定价、积分、sandbox 计费：同步更新 `architecture.md`、`release-gate-checklist.md`、`troubleshooting.md`
12. 改全局视觉基准、tokens、共享 UI primitives、Workbench/Prism/Admin 页面母版：同步更新 `wenjin-research-navigation-uiux.md`
