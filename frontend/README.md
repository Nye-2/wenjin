# 问津 Wenjin Frontend

更新时间：2026-04-20

前端是问津 workbench 的统一交互层，负责 workspace、thread（路由为 `/chat`）、feature、artifact、activity 与 LaTeX 主稿台的界面编排。

## 技术栈

- Next.js 16 App Router
- React 19
- TypeScript
- Tailwind CSS
- Zustand
- Axios

## 当前功能模块

- 登录注册与鉴权跳转
- workspace 列表与 workspace 工作台
- thread 主链路：主对话、skill 入口、streaming、任务状态、线程恢复
- knowledge/activity 面板：artifact、activity、follow-up、任务详情
- feature host：按后端 registry 动态渲染 feature 入口与结果
- LaTeX 主稿台：文件树、PDF 预览、反馈改写、导出

## 目录结构

```text
frontend/
├── app/                                   # App Router pages
│   └── (workbench)/workspaces/[id]/       # Workspace workbench
├── components/                            # Shared UI components
├── stores/                                # Zustand stores
├── lib/                                   # API clients, routing helpers, workspace contracts
├── hooks/                                 # Event stream and workspace hooks
└── proxy.ts                               # Route-level auth redirect
```

## 交互架构

### Thread Route (`/chat`)

- canonical route: `/workspaces/[id]/chat`
- feature/skill 通过 query seed 和首轮 orchestration metadata 进入 chat 主链
- streaming 响应、任务事件、thread 刷新都在 workspace stores 中统一处理

### Feature

- feature 列表与元数据来自后端 registry
- 前端不再硬编码旧的 feature slug 页面跳转链
- feature 执行后统一依赖 task 状态与 `refresh_targets` 刷新资源

### Activity / Follow-up

- activity detail dialog 会展示执行摘要、提示词、follow-up prompt
- feature 完成后的 follow-up 建议直接回落到 chat，而不是走并行页面

## 本地开发

```bash
cd frontend
npm install
npm run dev
```

质量检查命令：

```bash
npm run lint
npm run typecheck
npm run test
```

默认开发 API 基址：

- `NEXT_PUBLIC_API_URL` 未设置时，使用 `http://localhost:8001/api`

## 相关文档

- `../README.md`
- `../docs/documentation-map.md`
- `../docs/product/workspace-current-state.md`
- `../docs/product/frontend-feature-plugin-contract.md`
- `../docs/infrastructure/troubleshooting.md`
