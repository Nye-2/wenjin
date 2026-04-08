# Wenjin Documentation

更新时间: 2026-04-03

本目录按“当前事实源 + 历史归档”组织:

- `architecture/`: 系统架构、API 面、核心执行链路
- `infrastructure/`: 部署、环境变量、运维排障
- `product/`: 产品能力、功能目录、前后端契约
- `plans/`: 历史阶段性设计/实施记录（归档，不作为当前事实源）

## 快速入口

- 架构总览: `docs/architecture/README.md`
- 基础设施总览: `docs/infrastructure/README.md`
- 产品功能总览: `docs/product/README.md`
- 历史计划索引: `docs/plans/README.md`

## 文档治理规则

- 当前行为、接口、路由以 `docs/product/` 与 `docs/architecture/` 标注“当前”的文档为准。
- `docs/plans/` 与 `backend/docs/plans/` 仅保留历史决策和执行痕迹，不直接作为实现依据。
- 变更功能时，优先更新对应的产品文档与架构文档，再更新 README 引用。
- 所有部署步骤以 `docs/infrastructure/deployment-runbook.md` 为准。
