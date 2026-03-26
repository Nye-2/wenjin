# Troubleshooting

更新时间: 2026-03-19

## 1. `./start.sh` 卡在“等待 LangGraph 启动”

### 排查步骤

```bash
./start.sh --logs langgraph
tail -n 100 /home/cjz/academiagpt-v2/logs/langgraph.log
```

常见原因:

- Docker 不可用，LangGraph 无法启动
- `backend/.env` 缺失关键配置，LangGraph 进程启动即退出
- 端口 `2024` 已被占用

修复建议:

1. 确认 `docker ps` 可正常执行。
2. 停掉占用端口的进程: `lsof -i :2024`。
3. 单独启动验证: `./start.sh --langgraph`。

## 2. Compose 启动后 API 不可用

### 快速检查

```bash
docker compose ps
docker compose logs -f migrate
docker compose logs -f gateway
```

高频问题:

- `migrate` 失败导致 `gateway/langgraph` 不会启动
- `backend/.env` 未配置导致容器内运行时报错
- 数据库连接串与 compose 网络不匹配

修复建议:

1. 优先修复 `migrate` 报错后重启: `docker compose up -d migrate gateway langgraph`。
2. 确认容器内 DB 地址使用 `postgres:5432`、Redis 使用 `redis:6379`。

## 3. 前端提示 `Failed to fetch`

常见根因:

- Gateway 未启动/未健康
- 前端请求地址配置错误（`NEXT_PUBLIC_API_URL`）
- 反向代理路径未转发到 `/api`

补充说明:

- 如果没有创建 `frontend/.env.local`，开发环境默认会请求 `http://localhost:8001/api`。

排查命令:

```bash
curl -i http://localhost:8001/readyz
curl -i http://localhost:2026/health
curl -i http://localhost:2026/langgraph/info
curl -i http://localhost:2026/api/auth/me
```

若浏览器报 `Failed to fetch`，优先看 Network 面板中的实际请求 URL 与状态码。

## 4. SMTP 已配置但收不到验证码

按顺序检查:

1. `SMTP_ENABLED=true`
2. `SMTP_HOST`/`SMTP_PORT`/`SMTP_USERNAME`/`SMTP_PASSWORD` 是否可从后端机器连通
3. 后端日志是否出现 `发送邮件失败`
4. 是否触发频控（`SMTP_SEND_INTERVAL`）或日限额（`SMTP_DAILY_LIMIT`）

提示:

- 验证码格式为 6 位数字；输入时不区分大小写的问题已不适用。
- 当 `SMTP_ENABLED=false` 时不会发真实邮件，只能在日志/Redis 中看到验证码。

## 5. 功能执行后无结果刷新

检查任务结果中的 `refresh_targets`:

- `artifacts` -> 前端应刷新成果列表
- `papers` -> 前端应刷新论文列表
- `workspace` -> 前端应刷新 workspace 基础信息

相关代码:

- `frontend/hooks/useFeatureTaskRunner.ts`
- `backend/src/task/handlers/workspace_feature_handler.py`
