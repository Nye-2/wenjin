# Architecture Docs

更新时间：2026-04-28

## 文档索引（Current）

- `adr-platform-boundaries.md`：router / application / task / feature 分层边界
- `api-surface-map.md`：网关 API 分组与活跃面
- `workspace-execution-pipeline.md`：thread、feature、task、artifact 的执行主链
- `feature-domain-architecture.md`：workspace feature 域架构边界与核心关系
- `tech-stack-and-main-chain.md`：端到端主链路与系统分层事实源

## 当前架构原则

- Chat 是 control plane，Compute 是 work plane，Feature 是 transaction plane
- feature 事务执行统一经过 `FeatureIngressService`（launch/resume）
- 显式 feature launch/resume 经 `ChatTurnRouter` 和 `FeatureCommandHandler` 直接进入 ingress
- Compute projection 从 execution/task/subagent/runtime/artifact/Prism metadata 聚合，不成为第二事实源
- feature metadata 以 registry 为单一事实源
- runtime policy 以 `runtime_profiles.py` 为事实源
- subagents 作为 Compute 内部 worker 能力存在，不是独立 public API 或产品主链
- thread message 只承载发起、追问、完成摘要和 pointer，不承载 feature 当前状态

## 使用说明

- 本目录描述系统如何组织与执行，不包含部署命令。
- 架构边界、主链路或模块职责变化时，优先更新本目录。
- 文档总导航见 `../documentation-map.md`。
