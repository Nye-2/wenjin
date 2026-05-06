# Refactor 文档索引

更新时间：2026-05-06

本目录集中存放问津架构收敛与迁移文档。当前项目仍处于开发阶段，没有真实用户和历史数据兼容负担，因此本轮迁移按一次性完成设计，不保留 fallback、兼容入口、双写、灰度或旧链路适配层。

## 活跃文档

| 文档 | 状态 | 说明 |
|---|---|---|
| [目标架构：Wenjin Compute Architecture](./target-architecture.md) | 📋 总纲 | 架构设计总纲，持续维护 |
| [一次性迁移计划](./migration-plan.md) | 📋 总纲 | 主迁移路线 |
| [Workspace Reference Library 重建工程任务书](./reference-library-rebuild-taskbook.md) | ⚠️ 核心已实现 | 7 表/7 服务/API/前端面板/Agent 工具已落地，少量扩展项待续 |
| [Reference Library SSOT 收敛 Review](./reference-library-ssot-convergence-review.md) | ✅ 已完成 | 验收记录，5 个 SSOT 问题已修复并通过验证 |
| [Workspace 功能完善收尾：下一阶段任务书](./workspace-functional-finalization-next-phase.md) | ⚠️ 种子已实现 | G-L 种子落地完成，剩余可扩展项见文档第 8 节 |
| [Landing Page 重设计规划](./landing-page-redesign-plan.md) | 📋 待启动 | 尚未开始 |

## 归档文档

已完成的规划文档移至 [archive/](./archive/)：

- Chat-first Workspace 功能落实规划 ✅
- Chat Document Upload + Layout Parsing 规划 ✅
- UI/UX Redesign 规划 ✅

## 迁移原则

1. Chat 是用户入口和控制台，不再拥有 feature 执行权。
2. Compute 是任务工作台，承载长任务过程、sandbox、文件、日志、runtime blocks、subagents 和 artifacts。
3. FeatureIngressService 是所有 feature launch/resume 的唯一领域入口。
4. ExecutionSession 是 feature 业务生命周期唯一事实源。
5. TaskRecord 是 worker 异步执行事实源。
6. Artifact 和 Activity 是最终产物与可追溯历史事实源。
7. AgentHarness、DeerFlow、Claude/Codex SDK 只能作为 Compute 内部执行能力，不接管 workspace、thread、billing、artifact 或 task lifecycle。
8. 本轮迁移可以删除旧实现、重命名接口、调整数据结构和重写测试，不保留对旧 chat-feature tool loop 的兼容。
