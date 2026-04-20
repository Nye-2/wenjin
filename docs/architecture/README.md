# Architecture Docs

更新时间：2026-04-20

## 文档索引（Current）

- `adr-platform-boundaries.md`：router / application / task / feature 分层边界
- `api-surface-map.md`：网关 API 分组与活跃面
- `workspace-execution-pipeline.md`：thread、feature、task、artifact 的执行主链
- `feature-domain-architecture.md`：workspace feature 域架构边界与核心关系
- `tech-stack-and-main-chain.md`：端到端主链路与系统分层事实源

## 当前架构原则

- chat 与 feature 共用同一执行平面，不再并行维护旧 skill runtime
- feature 事务执行统一经过 `FeatureIngressService`（launch/resume）
- feature metadata 以 registry 为单一事实源
- feature 域使用专职 leader runtime 编排 graph/subagents
- subagents 作为 worker 能力存在，不是独立产品主链
- thread 不再保留 direct feature bridge 兼容分支，只走 lead-agent + tool 主链

## 使用说明

- 本目录描述系统如何组织与执行，不包含部署命令。
- 架构边界、主链路或模块职责变化时，优先更新本目录。
- 文档总导航见 `../documentation-map.md`。
