# Architecture Docs

更新时间：2026-05-11

## 文档索引（Current）

- `adr-platform-boundaries.md`：router / application / task / capability 分层边界
- `api-surface-map.md`：网关 API 分组与活跃面
- `system-architecture.md`：全栈系统架构、核心数据模型、技术栈和开发规范
- `workspace-execution-pipeline.md`：capability 执行主链（chat_agent → LeadAgentRuntime v2 → subagents → output mapping → commit）
- `feature-domain-architecture.md`：capability 数据驱动架构、output mapping、rooms 闭环
- `tech-stack-and-main-chain.md`：端到端主链路与系统分层事实源

## 当前架构原则

- **双 Agent 拓扑**：Chat Agent（左面板）+ Lead Agent v2（右面板），1:1 映射
- **Capability 数据驱动**：YAML seed + DB-backed，`CapabilityResolver` 加载校验
- Capability 执行统一走 `launch_feature` tool → `ExecutionService` → Celery → `LeadAgentRuntime`
- **Output mapping**：`OutputMappingResolver` 将 subagent 输出转为 5 种 typed `ResultOutput`，ResultCard 展示后用户 commit 到 rooms
- **8 workspace rooms**：Library / Documents / Decisions / Memory / Run History / Sandbox / Tasks / Settings
- feature metadata 以 registry 为单一事实源
- runtime policy 以 `runtime_profiles.py` 为事实源
- v2 subagents 以 `subagents/v2/registry.py` 为注册中心
- thread message 只承载发起、追问、完成摘要和 pointer，不承载执行当前状态

## 使用说明

- 本目录描述系统如何组织与执行，不包含部署命令。
- 架构边界、主链路或模块职责变化时，优先更新本目录。
- 文档总导航见 `../documentation-map.md`。
