# 问津 Wenjin Frontend

更新时间：2026-07-11

前端是问津科研工作台的统一交互层，负责 workspace shell、WorkspaceAgent 对话入口、MissionView、Prism 主稿台、Reference Library、Review/Commit 与 Admin Console。

## 技术栈

- Next.js 16 App Router
- React 19
- TypeScript
- Tailwind CSS
- Zustand
- Axios

## 当前功能模块

- 登录注册与鉴权跳转
- Workspace 列表与科研工作台 shell
- Chat Panel：主对话、streaming、Mission 启动与 steer、任务反馈、结果回写
- MissionView：当前 Mission、阶段进度、Worker、证据、产物、review items 与运行历史
- Prism：LaTeX 文件树、编辑器、编译、PDF 对照、AI 改稿、file-change preview/apply/revert
- Reference Library：文献列表、上传、导入、详情、BibTeX、source link 回跳
- Admin Console：模型目录、MissionPolicy/WorkerSkill 目录、定价、积分与系统配置

## 关键目录

```text
frontend/
├── app/
│   └── (workbench)/workspaces/[id]/       # Workspace workbench and Prism surface
├── components/                            # Shared UI primitives
├── stores/                                # Zustand stores
├── lib/                                   # API clients, routing helpers, contracts
├── hooks/                                 # Event stream and workspace hooks
├── tests/                                 # Unit and E2E tests
└── proxy.ts                               # Route-level auth redirect
```

## 交互架构

### Workspace Chat Entry

- Canonical route: `/workspaces/[id]`
- WorkspaceAgent 是 Mission 启动入口；前端不做关键词硬路由或第二套路由器。
- Streaming response、workspace events、Mission refresh 和 thread 恢复都在 workspace stores 中统一处理。

### MissionView

- 当前 Mission、Worker、候选结果、证据预览和运行历史统一读取 Mission API projection。
- Chat receipt 与 Mission Console 共享 `frontend/lib/api/missions.ts` 的规范化视图。
- 前端 store 只保存 UI focus、badge、panel state，不承载 Mission 业务事实。
- 默认 UI 不展示 raw stdout/stderr、raw args、template id、schema id 或日志墙。

### Prism

- Prism 是 workspace-owned manuscript/material surface。
- LaTeX adapter route 是主稿读写、编译、PDF 对照和 review apply/reject/revert 的唯一前端入口。
- AI 改稿与批注变更先进入 review item，用户确认后才写入主稿。

### Mission Entry

- MissionPolicy 与 WorkerSkill 元数据来自后端 DataService catalog。
- Mission 启动、artifact follow-up 和 retry 都回到 workspace chat，不建立独立任务 slug 页面。
- 执行完成后依赖 Mission projection、review items 和 commit receipts 刷新资源。

## 本地调试

项目标准运行方式见根目录 `README.md`：`docker compose up -d`。

单独调试前端：

```bash
cd frontend
npm install
npm run dev
```

质量检查命令：

```bash
npm run lint
npm run typecheck
npm test
npx vitest run
```

默认开发 API 基址：

- 前后端共享仓库根目录 `.env`；前端不再使用独立的 `frontend/.env.local`
- `NEXT_PUBLIC_API_URL` 未设置时，使用同源 `/api`
- `npm run dev` 在开发态把 `/api/*` 代理到 `WENJIN_DEV_API_PROXY_TARGET`
- 默认代理目标是 `http://localhost:8001`；如需连接 Docker/Nginx 入口，可设置 `WENJIN_DEV_API_PROXY_TARGET=http://localhost:2026`

## 相关文档

- `../README.md`
- `../docs/current/documentation-map.md`
- `../docs/current/workspace-current-state.md`
- `../docs/current/frontend-mission-contract.md`
- `../docs/current/wenjin-research-navigation-uiux.md`
- `../docs/current/troubleshooting.md`
