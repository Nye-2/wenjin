# Wenjin Current Docs Map

更新时间：2026-06-05
状态：Current

本目录是 Wenjin 当前实现的唯一事实源目录。后续开发、联调、review、发布前检查，优先只看这里。

## 1. 核心入口

| 文档 | 用途 |
| --- | --- |
| `architecture.md` | 唯一当前架构总览；execution-first 主链、边界、开发约束 |
| `workspace-current-state.md` | workspace / thread / execution / compute / ResultCard 当前行为 |
| `frontend-feature-plugin-contract.md` | capability entry / thread / execution 契约 |
| `workspace-feature-catalog.md` | workspace type / capability entry / skill 当前目录 |
| `workspace-reference-library.md` | Reference Library 当前事实源 |
| `wenjin-research-navigation-uiux.md` | 当前 UIUX / 视觉系统事实源；System-Grade Research Workbench 与 2026-06-05 full-shell migration 基准 |
| `release-gate-checklist.md` | 发布与回归门禁 |

## 2. 运维与环境

| 文档 | 用途 |
| --- | --- |
| `deployment-runbook.md` | 本地与 Compose 部署运行手册 |
| `environment-variables.md` | 环境变量基线 |
| `troubleshooting.md` | 常见问题排查 |

## 3. 长期方向与历史

| 文档 | 用途 |
| --- | --- |
| `strategy-seed.md` | 长期方向种子；不是当前实现契约 |
| `../superpowers/` | 历史 spec / plan / implementation record；除非本目录明确引用，否则不作为当前事实源 |

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
4. 改 capability / skill 目录或兼容入口映射：更新 `workspace-feature-catalog.md`
5. 改 references / evidence / bibtex / usage trace：更新 `workspace-reference-library.md`
6. 改 workspace-owned Prism route、review item、source link、protected section、agent manuscript context：更新 `workspace-current-state.md`、`architecture.md`、`frontend-feature-plugin-contract.md`
7. 改部署、端口、环境变量、排障：更新 `deployment-runbook.md`、`environment-variables.md`、`troubleshooting.md`
8. 改发布验收口径：更新 `release-gate-checklist.md`
9. 改 Chat run stream、`tool_invocation`/`tool_result`、RunView、Runs drawer、LiveWorkflowPanel：同步更新 `architecture.md`、`workspace-current-state.md`、`frontend-feature-plugin-contract.md`、`release-gate-checklist.md`
10. 改 admin dashboard、模型目录、定价、积分、sandbox 计费：同步更新 `architecture.md`、`release-gate-checklist.md`、`troubleshooting.md`
11. 改全局视觉基准、tokens、共享 UI primitives、Workbench/Prism/Admin 页面母版：同步更新 `wenjin-research-navigation-uiux.md`
