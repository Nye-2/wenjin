# Software Copyright Workspace 开发路线（2026-03-13）

## 1. 当前状态

registry 中 `software_copyright` 已定义：

1. `copyright_materials`
2. `technical_description`

当前实现状态：

1. `copyright_materials`：已实现真实 handler（可落库、可回显、可测试）。
2. `technical_description`：尚未实现具体 handler（当前为 placeholder 行为）。

---

## 2. 第一阶段目标

以当前已跑通 feature 为基础，优先补齐：

1. `technical_description`（P0）

完成后该 workspace 将具备“材料清单 + 技术说明”双闭环。

---

## 3. P0: technical_description 详细路线

### 后端

1. 在 `backend/src/workspace_features/services/` 中新增或扩展：
   - `build_technical_description_payload(...)`
2. 输入建议：
   - 软件名称、版本、核心模块、部署架构、数据库/中间件、接口协议。
3. 输出建议结构：
   - `system_overview`
   - `module_design`
   - `data_flow`
   - `deployment_architecture`
   - `security_and_permissions`
   - `operation_steps`
4. artifact 类型：
   - `technical_description`
5. 降级策略：
   - LLM 不可用时生成“章节骨架 + 待补字段清单”。
6. 在 `software_copyright.py` 中注册 `software_copyright.technical_description` handler。

### 前端

1. 新增页面：`.../technical-description/page.tsx`。
2. 可复用 thesis 的表单+轮询模板。
3. 支持从 `copyright_materials` artifact 读取已填信息作为默认值。

### Dashboard

新增聚合：

1. `copyright_materials.status`
2. `technical_description.status`

---

## 4. 第二阶段建议（可选）

1. 增加“材料一致性检查”feature（名称/版本/模块在材料、代码页、说明书中是否一致）。
2. 增加“提交前核对单”feature（输出最终 checklist）。

---

## 5. 测试建议

1. `tests/task/test_software_copyright_handlers.py`
   - 新增 `technical_description` 用例。
2. `tests/gateway/routers/test_features.py`
   - 覆盖 execute payload 与 handler_key 路由。
3. `tests/services/test_dashboard_service.py`
   - 覆盖双模块状态聚合。

---

## 6. 估算与里程碑

1. P0：1-2 天
2. 第二阶段（可选）：1-2 天

第一阶段可交付时间：约 2 天。
