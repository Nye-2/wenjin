# Refactor 文档索引

更新时间：2026-04-30

本目录集中存放问津下一轮架构收敛与迁移文档。当前项目仍处于开发阶段，没有真实用户和历史数据兼容负担，因此本轮迁移按一次性完成设计，不保留 fallback、兼容入口、双写、灰度或旧链路适配层。

## 文档

- [目标架构：Wenjin Compute Architecture](./target-architecture.md)
- [一次性迁移计划](./migration-plan.md)
- [Chat-first Workspace 功能落实规划](./chat-first-workspace-functional-plan.md)
- [Workspace 功能完善收尾：下一阶段任务书](./workspace-functional-finalization-next-phase.md)
- [Workspace Reference Library 重建工程任务书](./reference-library-rebuild-taskbook.md)
- [Reference Library SSOT 收敛 Review](./reference-library-ssot-convergence-review.md)

## 迁移原则

1. Chat 是用户入口和控制台，不再拥有 feature 执行权。
2. Compute 是任务工作台，承载长任务过程、sandbox、文件、日志、runtime blocks、subagents 和 artifacts。
3. FeatureIngressService 是所有 feature launch/resume 的唯一领域入口。
4. ExecutionSession 是 feature 业务生命周期唯一事实源。
5. TaskRecord 是 worker 异步执行事实源。
6. Artifact 和 Activity 是最终产物与可追溯历史事实源。
7. AgentHarness、DeerFlow、Claude/Codex SDK 只能作为 Compute 内部执行能力，不接管 workspace、thread、billing、artifact 或 task lifecycle。
8. 本轮迁移可以删除旧实现、重命名接口、调整数据结构和重写测试，不保留对旧 chat-feature tool loop 的兼容。
