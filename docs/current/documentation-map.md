# Wenjin Current Docs Map

更新时间：2026-05-22
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
| `workspace-prism-surface-release-notes.md` | workspace-owned Prism 当前发布说明与验证口径 |
| `release-gate-checklist.md` | 发布与回归门禁 |
| `../superpowers/plans/2026-05-22-workspace-execution-experience-convergence.md` | workspace execution UX 收敛实现记录；当前已合入主线 |

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
| `execution-review-history.md` | 统一执行架构历史 review 摘要；只保留追溯价值 |
| `../superpowers/specs/2026-05-20-wenjin-native-prism-integration-overview.md` | Prism 与 Wenjin workspace 深度适配的产品级 overview；定义当前 canonical Prism integration 的产品边界 |

## 4. 推荐阅读顺序

1. `docs/README.md`
2. `docs/current/documentation-map.md`
3. `docs/current/architecture.md`
4. `docs/current/workspace-current-state.md`
5. `docs/current/frontend-feature-plugin-contract.md`
6. 涉及 execution UX / Runs / Live panel 时看 `docs/superpowers/plans/2026-05-22-workspace-execution-experience-convergence.md`
7. 涉及 Prism 主稿链路时看 `docs/current/workspace-prism-surface-release-notes.md`
8. 需要时再看对应专题

## 5. 提交前维护清单

1. 改 execution / task / compute / thread 边界：更新 `architecture.md`
2. 改 workspace / thread / ResultCard / refresh / 恢复行为：更新 `workspace-current-state.md`
3. 改 capability entry / thread / execution 公共契约：更新 `frontend-feature-plugin-contract.md`
4. 改 capability / skill 目录或兼容入口映射：更新 `workspace-feature-catalog.md`
5. 改 references / evidence / bibtex / usage trace：更新 `workspace-reference-library.md`
6. 改 workspace-owned Prism route、review item、source link、protected section、agent manuscript context：更新 `workspace-current-state.md`、`architecture.md`、`workspace-prism-surface-release-notes.md`
7. 改部署、端口、环境变量、排障：更新 `deployment-runbook.md`、`environment-variables.md`、`troubleshooting.md`
8. 改发布验收口径：更新 `release-gate-checklist.md`
9. 改 Chat run stream、`tool_invocation`/`tool_result`、RunView、Runs drawer、LiveWorkflowPanel：同步更新 `architecture.md`、`workspace-current-state.md`、`frontend-feature-plugin-contract.md`、`release-gate-checklist.md`
