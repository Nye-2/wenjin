# AcademiaGPT v2 Documentation

更新时间: 2026-03-19

本目录只保留当前可执行、可维护、可追溯的文档，按照三类组织:

- `architecture/`: 系统架构、API 面、核心执行链路
- `infrastructure/`: 部署、环境变量、运维排障
- `product/`: 产品能力、功能目录、前后端契约

## 快速入口

- 架构总览: `docs/architecture/README.md`
- 基础设施总览: `docs/infrastructure/README.md`
- 产品功能总览: `docs/product/README.md`

## 文档治理规则

- 历史阶段性计划/临时执行手册不再放在 `docs/` 根目录。
- 变更功能时，优先更新对应的产品文档与架构文档，再更新 README 引用。
- 所有部署步骤以 `docs/infrastructure/deployment-runbook.md` 为准。
