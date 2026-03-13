# LLM 模型分层精简与路由方案（2026-03-13）

## 1. 方案目标

在保留“多模型路由 + 用户可选模型”能力的前提下，精简当前模型体系，降低配置和运维复杂度。

目标收敛为三类模型：

1. `utility`：便宜、稳定、仅供系统内部使用，用户不可见，原则上只保留 1 个。
2. `generation`：高质量主模型池，负责规划/思考/生成，用户可选。
3. `image`：图片生成模型池，用户可选。

---

## 2. 当前状态与问题

### 2.1 现状（代码事实）

1. `workspace_features` 侧普遍通过 `get_gen_models()` + `preferred_model or models[0]` 选模型。
2. 前端 workspace 页面目前没有统一透传 `model_id`，导致多数执行落在默认生成模型。
3. `/api/models` 仍是静态硬编码列表，和 `.env` 动态模型池不一致。
4. 低成本任务存在硬编码模型名（例如摘要中间件的 `"qwen-flash"`），缺少统一 `utility` 路由入口。
5. `LLM_TOOL_MODELS` 作为独立类别存在，但在当前主路径中业务价值有限，增加维护负担。

### 2.2 核心问题

1. “有多模型配置”不等于“有稳定可控路由”。
2. 模型类别过多但职责边界不清晰，增加认知和排障成本。
3. 用户感知模型与系统实际执行模型存在偏差。

---

## 3. 目标架构

### 3.1 模型分层

1. `generation`（用户可选）
2. `image`（用户可选）
3. `utility`（系统内部固定，不对用户暴露）

`LLM_TOOL_MODELS` 进入兼容态：

1. 短期可继续读取，避免一次性破坏旧环境。
2. 中期不再作为主分类对外暴露。
3. 后续版本标记为 deprecated 并逐步移除。

### 3.2 路由规则（统一优先级）

1. 生成任务：
   `request.model_id > workspace.default_gen_model_id > system.default_gen_model_id`
2. 生图任务：
   `request.image_model_id > workspace.default_image_model_id > system.default_image_model_id`
3. 内部轻任务（摘要、上下文压缩、轻量提取）：
   始终使用 `system.default_utility_model_id`

说明：

1. `utility` 类模型不出现在前端模型选择列表。
2. 用户只感知 `generation` 和 `image` 两类模型。

### 3.3 前后端契约

前端可见模型接口建议返回：

1. `id`
2. `model`
3. `name`
4. `category`（`generation`/`image`）
5. `selectable`（布尔，`utility=false`）
6. `is_default`（可选）

---

## 4. 实施计划（分阶段）

## Phase A：后端基础能力收敛（优先）

目标：先让模型分类和默认路由可靠。

工作项：

1. 动态模型目录化：
   - 将 `/api/models` 从静态列表改为读取 `llm_config` 动态数据。
   - 返回模型类别与是否可选信息。
2. 配置统一：
   - 新增/约定系统默认模型 ID：
     - `DEFAULT_GEN_MODEL_ID`
     - `DEFAULT_IMAGE_MODEL_ID`
     - `DEFAULT_UTILITY_MODEL_ID`
   - 若默认 ID 未配置，回退到各类别第一个模型。
3. 路由入口函数：
   - 新增统一解析函数（按“请求 > workspace > 系统默认”）。
   - 供 `workspace_features`、chat、中间件复用。
4. 兼容策略：
   - 保留 `LLM_TOOL_MODELS` 读取能力，但不纳入主路由决策。
   - 启动日志中提示该分类将逐步废弃。

验收标准：

1. 后端可在无前端改动时稳定按默认模型执行。
2. `/api/models` 返回真实可用模型，不再与 `.env` 脱节。

## Phase B：workspace/聊天用户选模接入

目标：让“用户可选”真正生效。

工作项：

1. workspace 执行页面增加模型选择器（仅 `generation` 类）：
   - `sci`、`proposal` 先接入。
   - 通过 `params.model_id` 透传到 execute API。
2. 生图页面增加 `image` 模型选择器（仅相关 feature）。
3. chat 保持可选模型能力，并切换默认模型逻辑到 `generation` 默认模型。
4. 工作区级默认模型：
   - 可将 `default_gen_model_id/default_image_model_id` 存在 `workspace_config`。
   - 用户本工作区只需设置一次，减少重复选择。

验收标准：

1. 用户在页面选择模型后，任务结果 payload 中可追踪 `model_id`。
2. 不选模型时自动回退到 workspace 或系统默认。

## Phase C：内部轻任务切换到 utility

目标：把用户无感知的轻任务统一迁到便宜模型。

工作项：

1. 摘要中间件改为读取 `default_utility_model_id`，移除硬编码模型名。
2. 其他轻任务（如上下文管理、轻量提取）逐步切换到同一路由。
3. 为 utility 路径补充失败降级：
   - 失败时返回空摘要或保留原上下文，不阻断主任务。

验收标准：

1. utility 模型故障不影响主生成任务可用性。
2. 轻任务成本可观测下降（通过调用日志或成本统计验证）。

---

## 5. 配置建议（目标形态）

示例（示意，不含真实密钥）：

```bash
LLM_GEN_MODELS='[
  {"id":"glm-5","model":"glm-5","api_key":"***","base_url":"...","temperature":0.3,"max_tokens":4096},
  {"id":"backup-gen","model":"...","api_key":"***","base_url":"...","temperature":0.3,"max_tokens":4096}
]'

LLM_UTILITY_MODELS='[
  {"id":"cheap-utility","model":"...","api_key":"***","base_url":"...","temperature":0.1,"max_tokens":1024}
]'

LLM_IMAGE_MODELS='[
  {"id":"kling-v2-1","model":"kling-v2-1","api_key":"***","base_url":"..."}
]'

DEFAULT_GEN_MODEL_ID=glm-5
DEFAULT_UTILITY_MODEL_ID=cheap-utility
DEFAULT_IMAGE_MODEL_ID=kling-v2-1
```

---

## 6. 风险与对策

1. 风险：旧代码仍依赖静态模型名（如 `gpt-4o`、`qwen-flash`）。
   对策：统一迁移到“默认模型解析函数”，并保留兼容回退。
2. 风险：前端未透传 `model_id` 时，用户误以为已切换模型。
   对策：任务结果和 artifact 中回显 `model_id`，并在 UI 显示“本次使用模型”。
3. 风险：一次性移除 `LLM_TOOL_MODELS` 导致历史环境启动异常。
   对策：先兼容读取 + 启动告警，再分版本移除。

---

## 7. 讨论与决策点

待确认项：

1. `workspace_config` 是否作为默认模型持久化位置（推荐是）。
2. chat 默认模型是否与 workspace 默认生成模型联动，还是全局固定。
3. 是否在第一阶段就提供“模型能力标签”（如工具调用、视觉、JSON schema 支持）。

---

## 8. Definition of Done（本方案完成标准）

1. 模型体系对外仅强调三类：`utility`、`generation`、`image`。
2. 用户界面仅提供 `generation` 与 `image` 两类模型选择。
3. 内部轻任务稳定使用单一 utility 模型，用户无感知。
4. 所有任务可追踪本次实际使用的模型 ID。
5. 旧配置兼容可运行，并有清晰的废弃迁移提示。

