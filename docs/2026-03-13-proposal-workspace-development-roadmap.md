# Proposal Workspace 开发路线（2026-03-13）

## 1. 当前状态

registry 中 `proposal` 已定义 2 个 feature：

1. `proposal_outline`
2. `background_research`

当前缺口：

1. 无具体 `proposal.*` handler。
2. 前端无专属页面与参数表单。
3. 无 proposal 模块 dashboard 聚合指标。

---

## 2. 第一阶段目标

按“先结构、后内容”的顺序实现：

1. `proposal_outline`（P0，必须先做）
2. `background_research`（P1）

---

## 3. 详细开发路线

## 3.1 P0: proposal_outline

### 后端

1. 新增 `backend/src/workspace_features/services/proposal_feature_service.py`。
2. 实现 `build_proposal_outline_payload(...)`：
   - 输入：项目主题、申报类型（国自然/省部级/企业联合等）、周期。
   - 输出：章节结构（立项依据、研究目标、技术路线、计划进度、预算框架）。
3. 新增 handler：`proposal.proposal_outline`。
4. artifact 类型建议：
   - `proposal`（推荐）
   - 内容里分 `sections` + `milestones` + `risks`。
5. LLM 降级：
   - 模型不可用时输出固定可编辑模板。

### 前端

1. 新增页面：`.../proposal-outline/page.tsx`。
2. 通过统一轮询工具提交并拿结果：
   - `pollTaskUntilTerminal`。

### 验收

1. 能稳定产出 proposal 大纲 artifact。
2. 工作台最近产出可直接看到该 artifact。

## 3.2 P1: background_research

### 后端

1. 实现 `build_background_research_payload(...)`：
   - 输入：主题关键词、行业范围、时间范围。
   - 输出：现状综述、问题清单、可行技术方向。
2. handler 注册：`proposal.background_research`。
3. artifact 类型建议：
   - `background_research`
   - 可追加 `references` 字段。

### 前端

1. 新增页面：`.../background-research/page.tsx`。
2. 支持把研究结果一键“写入大纲上下文”。

---

## 4. Dashboard 建议

proposal workspace 建议聚合 2 个核心指标：

1. `proposal_outline.status`：是否已有 `proposal` artifact。
2. `background_research.count`：`background_research` artifact 数量。

---

## 5. 测试建议

1. `tests/task/test_proposal_handlers.py`
2. `tests/gateway/routers/test_features.py` 增加 proposal execute 覆盖
3. `tests/services/test_dashboard_service.py` 增加 proposal 状态覆盖

---

## 6. 估算与里程碑

1. P0：1 天
2. P1：1-2 天

第一阶段可交付时间：约 2-3 天。
