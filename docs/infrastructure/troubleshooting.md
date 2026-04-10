# Troubleshooting

更新时间：2026-04-10

以下命令默认你已经设置：

```bash
export REPO_ROOT=/path/to/your/wenjin/repo
cd "$REPO_ROOT"
```

## 1. `./start.sh` 启动后功能任务一直 pending

高频原因：

- worker 没有启动
- Redis 不可用
- `backend/.env` 缺少必要模型配置

排查：

```bash
./start.sh --status
./start.sh --logs worker
./start.sh --logs backend
```

修复：

1. 确认状态页里 `Worker` 为运行中。
2. 检查 `backend/.env` 的 `REDIS_URL`、模型配置和数据库连接。
3. 单独重启 worker：`./start.sh --worker`。

## 2. Compose 启动后 API 不可用

快速检查：

```bash
docker compose ps
docker compose logs -f migrate
docker compose logs -f gateway
docker compose logs -f worker
```

高频问题：

- `migrate` 失败导致主服务不启动
- `backend/.env` 未配置或配置与 compose 网络不匹配
- `gateway` 健康检查未通过

修复建议：

1. 先修复 `migrate` 报错，再重启：`docker compose up -d migrate gateway worker frontend nginx`
2. 确认容器内 DB 地址是 `postgres:5432`，Redis 地址是 `redis:6379`

## 3. 浏览器提示 `Failed to fetch`

常见原因：

- Gateway 未启动或 `/readyz` 不健康
- `NEXT_PUBLIC_API_URL` 配错
- 反向代理没有正确转发 `/api`

排查：

```bash
curl -i http://localhost:8001/readyz
curl -i http://localhost:2026/health
curl -i http://localhost:2026/api/auth/me
```

补充：

- 如果没有创建 `frontend/.env.local`，开发环境默认请求 `http://localhost:8001/api`
- 如果走 Nginx，前端通常通过同源 `/api` 访问

## 4. SSE 不流动或前端长时间无更新

检查项：

1. 代理层是否关闭了 SSE 缓冲
2. Gateway 日志中是否有流式异常
3. Worker 是否正常发布任务进度 / workspace events

排查：

```bash
./start.sh --logs backend
./start.sh --logs worker
docker compose logs -f nginx
```

## 5. SMTP 已配置但收不到验证码

按顺序检查：

1. `SMTP_ENABLED=true`
2. `SMTP_HOST` / `SMTP_PORT` / `SMTP_USERNAME` / `SMTP_PASSWORD` 是否可连通
3. backend 日志里是否出现 `发送邮件失败`
4. 是否触发频控或日限额

提示：

- 当 `SMTP_ENABLED=false` 时不会发送真实邮件，只会写日志和 Redis
- 验证码格式固定为 6 位数字

## 6. 功能执行后无结果刷新

检查任务结果中的 `refresh_targets`：

- `artifacts`：前端刷新成果列表
- `papers`：前端刷新论文列表
- `workspace`：前端刷新 workspace 基础信息

相关代码：

- `frontend/lib/workspace-feature-execution.ts`
- `frontend/app/(workbench)/workspaces/[id]/components/ChatPanel.tsx`
- `backend/src/task/handlers/workspace_feature_handler.py`
