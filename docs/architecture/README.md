# Architecture Docs

更新时间：2026-04-10

## 文档索引

- `adr-platform-boundaries.md`：router / application / task / feature 分层边界
- `api-surface-map.md`：网关 API 分组与活跃面
- `workspace-execution-pipeline.md`：chat、feature、task、artifact 的执行主链

## 当前架构原则

- chat 与 feature 共用同一执行平面，不再并行维护旧 skill runtime
- `run_workspace_feature` 是 chat 到 feature 的唯一显式执行入口
- feature metadata 以 registry 为单一事实源
- subagents 作为 worker 能力存在，不是独立产品主链

## 使用说明

- 本目录描述系统如何组织与执行，不包含部署命令。
- 架构边界、主链路或模块职责变化时，优先更新本目录。
