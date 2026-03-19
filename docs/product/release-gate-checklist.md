# Release Gate Checklist

更新时间: 2026-03-19

用于发布前 Go/No-Go 决策，覆盖五类 workspace 的核心可用性。

## 1. Core Gate (必须全绿)

1. workspace feature 执行主链路可用（提交、轮询、终态可见）。
2. 关键回归通过:
   - `tests/workspace_features/test_workspace_e2e_matrix.py`
   - `tests/gateway/routers/test_features.py`
   - `tests/application/handlers/test_feature_execution_handler.py`
3. 前端静态检查通过:
   - `npx tsc --noEmit`

## 2. Extended Gate (建议全绿)

1. 工具链/集成测试通过:
   - `tests/integration/test_tool_chain.py`
   - `tests/mcp/test_academic_tools.py`
   - `tests/integration/test_http_client.py`

## 3. Admin Release Gate API

- Endpoint: `GET /api/dashboard/admin/release-gate?include_extended=true`
- 权限: admin
- 用途: 统一输出发布门禁报告

## 4. Launch Checklist

- [ ] 五个 workspace 页面路由可达，无 404
- [ ] feature 可提交并返回 task_id
- [ ] 任务状态可从 pending/running 进入 success 或 failed
- [ ] 失败态有明确错误提示且可重试
- [ ] artifact 列表可反映最新产出
- [ ] SMTP 验证码链路（如启用）可稳定工作
