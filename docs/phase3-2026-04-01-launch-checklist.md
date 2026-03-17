# Phase 3 五 Workspace 上线清单（目标日期：2026-04-01）

## 1. 目标与范围

本清单用于 `2026-04-01` 五 workspace（`thesis/sci/proposal/software_copyright/patent`）同日上线前的 Go/No-Go 决策。

上线目标：

1. 五个 workspace 均可被真实用户使用（可触发、可执行、可产出、可追踪）。
2. `thesis` 输出固定中文；`sci` 输出固定英文。
3. 工作台状态与页面反馈语义一致（执行中、成功、失败可见且可重试）。

---

## 2. 门禁定义

### 2.1 Core Gate（阻断门禁，必须全绿）

1. 语言硬约束：`thesis=zh`，`sci=en`。
2. `workspace e2e matrix` 通过。
3. `features router` 回归通过。
4. `feature execution handler` 回归通过。
5. 前端 `TypeScript` 编译检查通过。

### 2.2 Extended Gate（非阻断门禁，建议全绿）

1. `tests/integration/test_tool_chain.py`
2. `tests/mcp/test_academic_tools.py`
3. `tests/integration/test_http_client.py`

说明：Extended Gate 若未通过，需记录 blocker 和修复计划，但不阻断 Core Gate 的 Go 结论。

---

## 3. 执行命令（发布前固定清单）

### 3.1 Core Gate 命令

```bash
cd /home/cjz/AcademiaGPT-V2/backend
PYTHONPATH=. uv run pytest \
  tests/workspace_features/test_workspace_e2e_matrix.py \
  tests/services/test_release_gate.py \
  tests/services/test_dashboard_service.py \
  tests/gateway/routers/test_features.py \
  tests/application/handlers/test_feature_execution_handler.py \
  tests/gateway/routers/test_dashboard.py \
  tests/gateway/routers/test_dashboard_center.py -q
```

```bash
cd /home/cjz/AcademiaGPT-V2/frontend
npx tsc --noEmit
```

### 3.2 Extended Gate 命令

```bash
cd /home/cjz/AcademiaGPT-V2/backend
PYTHONPATH=. uv run pytest \
  tests/integration/test_tool_chain.py \
  tests/mcp/test_academic_tools.py \
  tests/integration/test_http_client.py -q
```

### 3.3 Admin API（可选）

后端新增 admin-only 接口：`GET /dashboard/admin/release-gate`，支持 `include_extended` 参数。

示例：

```bash
curl -H "Authorization: Bearer <ADMIN_TOKEN>" \
  "http://localhost:8001/api/dashboard/admin/release-gate?include_extended=true"
```

说明：该接口会触发对应检查命令执行，适合发布前由管理员触发一次并保留报告。

### 3.4 CLI（推荐用于 CI）

```bash
cd /home/cjz/AcademiaGPT-V2/backend
PYTHONPATH=. uv run python -m src.quality.release_gate_cli --include-extended
```

可选参数：

- `--timeout-seconds 900`：调整单个检查超时时间。
- `--output /tmp/release-gate.json`：保存 JSON 报告。

退出码语义：

- `0`：Core Gate 通过（Go）。
- `1`：Core Gate 未通过（No-Go）。

---

## 4. 上线前检查项（Checklist）

- [ ] 5 个 workspace 均可从工作台进入对应模块页面，路由无 404。
- [ ] 页面执行反馈统一：`TaskFeedbackBanner` 可显示运行中/失败并支持重试。
- [ ] 结果信息层统一：关键页面已使用 `WorkspaceResultPanel`。
- [ ] Dashboard 模块四态正确：`not_started/in_progress/completed/failed`。
- [ ] `compile_export` 失败时展示 `failed`（不误报进行中）。
- [ ] `thesis_writing`、`proposal_outline`、`technical_description`、`patent_outline` 页面可稳定提交任务。
- [ ] artifact 列表可刷新并反映最新产出。
- [ ] `evaluate_release_gate()` 输出报告中 Core Gate 为 `passed`。
- [ ] 管理端发布门禁面板可展开失败项明细（命令/返回码/输出尾部/修复建议）。

---

## 5. 2026-03-16 基线结果（可追溯）

1. Core Gate 回归：`69 passed`。
2. Extended Gate 回归：`44 passed`。
3. Frontend `npx tsc --noEmit`：通过。

当日结论：当前基线满足继续推进上线准备的条件。

---

## 6. Go/No-Go 记录模板（2026-03-31 使用）

### 6.1 Core Gate

- 状态：`passed / failed`
- 失败项（若有）：
- 修复 owner：
- 预计恢复时间：

### 6.2 Extended Gate

- 状态：`passed / failed / pending`
- blocker（若有）：
- 风险说明：

### 6.3 最终决策

- 结论：`GO / NO-GO`
- 决策时间：
- 决策人：
- 备注：
