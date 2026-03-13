# Patent Workspace 开发路线（2026-03-13）

## 1. 当前状态

registry 中 `patent` 已定义：

1. `patent_outline`
2. `prior_art_search`

当前缺口：

1. 后端无 `patent.*` 具体 handler。
2. 前端无专属专利工作页。
3. dashboard 未对专利模块做聚合。

---

## 2. 第一阶段目标

按“先专利结构、后现有技术检索”顺序推进：

1. `patent_outline`（P0）
2. `prior_art_search`（P1）

---

## 3. 详细开发路线

## 3.1 P0: patent_outline

### 后端

1. 新增 `backend/src/workspace_features/services/patent_feature_service.py`。
2. 实现 `build_patent_outline_payload(...)`：
   - 输入：创新点描述、技术领域、应用场景、预期实施方式。
   - 输出：说明书结构（技术领域/背景技术/发明内容/附图说明/具体实施方式）和权利要求草案框架。
3. 新增 handler 注册：`patent.patent_outline`。
4. artifact 类型建议：
   - `patent_outline`
5. 降级策略：
   - 生成模板骨架 + “待补证据点”列表。

### 前端

1. 新增页面：`.../patent-outline/page.tsx`。
2. 用统一轮询模式完成闭环。

### 验收

1. 能产出可编辑的专利框架 artifact。
2. workspace 知识区可看到结构化章节。

## 3.2 P1: prior_art_search

### 后端

1. 实现 `build_prior_art_search_payload(...)`：
   - 输入：关键词、IPC/CPC（可选）、时间范围。
   - 输出：现有技术对比清单、新颖性风险点、规避建议。
2. handler 注册：`patent.prior_art_search`。
3. artifact 类型建议：
   - `prior_art_report`
   - 可附 `comparison_table`。

### 前端

1. 新增页面：`.../prior-art-search/page.tsx`。
2. 支持从检索结果回填到 `patent_outline` 页面作为约束条件。

---

## 4. Dashboard 建议

建议增加两项：

1. `patent_outline.status`
2. `prior_art_search.count`

---

## 5. 测试建议

1. `tests/task/test_patent_handlers.py`
2. `tests/gateway/routers/test_features.py` 增加 patent payload 断言
3. `tests/services/test_dashboard_service.py` 增加 patent 状态聚合断言

---

## 6. 估算与里程碑

1. P0：1-2 天
2. P1：2 天

第一阶段可交付时间：约 3-4 天。
