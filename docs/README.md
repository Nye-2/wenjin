# Wenjin Docs

更新时间：2026-04-28

本目录只保留当前实现的事实源文档，覆盖架构、产品契约、基础设施与文档治理入口。

## 快速入口

- `documentation-map.md`：全量文档导航（推荐先读）
- `architecture/README.md`：系统分层、主链路、API surface
- `product/README.md`：workspace/thread/feature 当前行为与前后端契约
- `infrastructure/README.md`：部署、环境变量、运行与排障

## 文档分层（Current）

- `architecture/`：Chat/Compute/Feature 执行平面、线程/运行链路、API 面
- `product/`：workspace/thread/Compute/WenjinPrism 行为、前后端契约、发布门禁
- `infrastructure/`：部署、环境变量、排障与压测

## 推荐阅读顺序

1. `README.md`
2. `docs/documentation-map.md`
3. `docs/architecture/README.md`
4. `docs/product/README.md`
5. `docs/infrastructure/README.md`

## 已清理历史文档（2026-04-15）

- `docs/architecture/deer-flow-upstream-migration-playbook.md`
- `docs/architecture/feature-catalog-v2-plan.md`
- `docs/architecture/feature-domain-implementation-plan.md`
- `docs/architecture/wenjinprism-integration-plan.md`
- `docs/thesis/generate_word_draft.py`

以上文档均为阶段性迁移/实施材料，当前主链路已落地，继续保留会造成事实源混淆；追溯请使用 Git 历史。

## 治理规则（必须执行）

- 文档仅保留 `Current` 事实源；阶段性执行稿完成后应清理，而不是长期并存。
- 任何影响架构、接口、运行方式、前端交互的变更，都必须同步更新对应文档。
- 文档与实现冲突时，以实现为准，并在同一改动中回补文档。
- 提交前至少完成一次文档入口检查：`README.md`、`docs/README.md`、`docs/documentation-map.md`、`backend/README.md`、`frontend/README.md`。
