# Chat Pipeline 修复清单

## 问题来源

v2 workspace rebuild 后 chat 链路存在多个功能缺失和 bug。以下按严重程度分级。

---

## Critical — 阻塞正常使用

### C1: 消息不持久化，刷新全丢

- **位置**: `frontend/stores/chat-store.ts` L118
- **现状**: Zustand 纯内存 store，`messages: []` 初始化，无 persist middleware
- **影响**: 页面刷新 = 对话清空。用户无法回顾历史
- **已有条件**:
  - `zustand/middleware` 的 `persist` 已在 `locale.ts`、`auth.ts` 中使用
  - 后端 `POST /workspaces/{id}/thread` 返回 thread 的所有 messages
  - 后端 `GET /threads/{id}/state` 也返回完整消息列表
- **修复**: 加载历史消息 + Zustand persist（localStorage 缓存，API 回源）

### C2: structured_output 解析几乎必败

- **位置**: `backend/src/agents/lead_agent/structured_output.py` L44
- **现状**: `with_structured_output(AgentMessage)` 要求 LLM 输出 JSON，MiMo 模型几乎不遵守
- **影响**:
  - 每次都走 fallback，log 里大量 `structured_output_failed`
  - 之前 fallback 多调一次 LLM 导致双重复回复（已修），但根因未解
- **修复**: 当 `with_structured_output` 失败时，直接用原始文本包装为 TextBlock，不再尝试二次 LLM 调用

### C3: Middleware 查已归档表污染事务

- **位置**: `backend/src/agents/middlewares/literature_context.py`, `knowledge_context.py`
- **现状**: 查 `workspace_references` 表，但 042 migration 已将其改名为 `_legacy_workspace_references`
- **影响**: SQL 错误 → 事务中止 → 后续所有 SQL 全挂 → "AI 服务内部错误"
- **临时修复**: 已用 `begin_nested()` savepoint 隔离（已部署）
- **根治**: 迁移 middleware 到新的 reference 表，或暂时禁用

---

## Important — 影响体验

### I1: 无文件上传按钮

- **位置**: `frontend/app/(workbench)/workspaces/[id]/v2/components/ChatPanel.tsx`
- **现状**: 输入区只有文本 input + 发送按钮，无附件/上传 UI
- **已有条件**:
  - 后端 `POST /threads/{threadId}/uploads` 支持 file upload（max 20 files, 100MB/file）
  - `RunCreateRequest.attachments` 支持 `RunAttachment[]`
  - 前端 `lib/api/threads.ts` 已有 `uploadThreadFiles()` API client
- **修复**: 在输入框左侧加 `+` 按钮 → 选择文件 → 上传 → 作为 attachment 发送

### I2: 无 Markdown 渲染

- **位置**: `frontend/app/(workbench)/workspaces/[id]/v2/components/MessageBlock.tsx` L16
- **现状**: `whiteSpace: "pre-wrap"` 纯文本显示，Markdown 格式全部丢失
- **已有条件**: `react-markdown` (^10.1.0) 和 `remark-gfm` (^4.0.1) 已在 package.json
- **修复**: text block 用 `<ReactMarkdown>` 渲染，配合 v2 样式

### I3: 单行输入框

- **位置**: `ChatPanel.tsx` L186
- **现状**: 用 `<input>` 元素，不支持多行输入、粘贴长文本
- **修复**: 替换为 `<textarea>`，支持 Enter 发送 + Shift+Enter 换行

### I4: 无对话历史加载

- **位置**: `chat-store.ts`
- **现状**: `sendMessage` 调用 `ensure_thread` 但从不读取返回的 messages
- **影响**: 每次进入 workspace 对话都是空的，即使有历史消息
- **修复**: `ensure_thread` 返回后，将已有 messages 加载到 store

### I5: thinking block 显示模型内部对话

- **位置**: `MessageBlock.tsx` L20-30, `ThinkingBlock.tsx`
- **现状**: MiMo 的 reasoning 内容常包含模型自我身份声明（"我是 MiMo..."），直接展示给用户
- **修复**: 过滤 reasoning 内容中的模型自我声明，或仅显示首段

---

## Minor — 锦上添花

### M1: 无消息重新生成
### M2: 无 model selector
### M3: 无 thread/conversation 切换
### M4: question_card 渲染简陋（pills 不可点击）
### M5: 无错误重试机制

---

## 依赖关系

```
C1 (消息持久化) ──depends on── I4 (历史加载)
I1 (文件上传) ──independent
I2 (Markdown) ──independent
I3 (多行输入) ──independent
C2 (structured_output) ──independent
C3 (middleware) ──independent
I5 (thinking filter) ──independent
```

## 已修复（本次会话）

- ✅ Middleware savepoint 隔离（C3 临时）
- ✅ structured_output fallback 不再二次调 LLM（C2 缓解）
- ✅ 输入框 sending 期间可编辑
- ✅ "思考中..." 指示器
