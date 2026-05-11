# Chat Pipeline 修复计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 v2 workspace chat pipeline 的 6 个关键问题：消息持久化、Markdown 渲染、多行输入、文件上传、structured_output 修复、thinking 内容过滤。

**Architecture:** 前端修改为主（ChatPanel、MessageBlock、chat-store），后端仅需 small fix（structured_output）。按依赖顺序执行：先修 C1/C2 阻塞性问题，再逐个修复体验问题。

**Tech Stack:** React 19, TypeScript, Zustand (persist middleware), react-markdown + remark-gfm (已在 package.json), Tailwind, v2 CSS tokens

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `frontend/stores/chat-store.ts` | MODIFY | 加 loadHistory + persist + 修复 ensure_thread 后加载消息 |
| `frontend/app/(workbench)/workspaces/[id]/v2/components/ChatPanel.tsx` | MODIFY | textarea 替换 input，加文件上传按钮 |
| `frontend/app/(workbench)/workspaces/[id]/v2/components/MessageBlock.tsx` | MODIFY | text block 用 ReactMarkdown 渲染 |
| `frontend/app/(workbench)/workspaces/[id]/v2/components/ThinkingBlock.tsx` | MODIFY | 过滤模型自我声明 |
| `frontend/app/(workbench)/workspaces/[id]/v2/components/FileAttachButton.tsx` | CREATE | 文件选择 + 上传 + 附件预览 |
| `backend/src/agents/lead_agent/structured_output.py` | MODIFY | fallback 直接用 prompt 文本（已修，验证确认） |

---

### Task 1: 消息历史加载（C1 + I4）

**Files:**
- Modify: `frontend/stores/chat-store.ts`

- [ ] **Step 1: 添加 loadHistory 方法到 store**

在 `ChatState` interface 中添加：

```typescript
interface ChatState {
  messages: Message[];
  currentAssistantId: string | null;
  isSending: boolean;
  handleEvent(event: ChatEvent): void;
  sendMessage(workspaceId: string, content: string): Promise<void>;
  loadHistory(workspaceId: string): Promise<void>;
  reset(): void;
}
```

在 store implementation 中添加 `loadHistory` 方法：

```typescript
async loadHistory(workspaceId: string) {
  const { messages } = get();
  if (messages.length > 0) return; // 已有消息，不重复加载

  try {
    const res = await authorizedFetch(
      `/api/workspaces/${workspaceId}/thread`,
      { method: "POST", headers: { "Content-Type": "application/json" } },
    );
    if (!res.ok) return;
    const thread = await res.json();

    if (thread.messages && thread.messages.length > 0) {
      const loaded: Message[] = thread.messages.map((m: Record<string, unknown>) => ({
        id: (m.id as string) || crypto.randomUUID(),
        role: (m.role as "user" | "assistant" | "system") || "assistant",
        blocks: Array.isArray(m.blocks) ? m.blocks : [{ kind: "text" as const, content: String(m.content || "") }],
        createdAt: (m.created_at as string) || new Date().toISOString(),
      }));
      set({ messages: loaded });
    }
  } catch {
    // 静默失败，空 state 也能用
  }
},
```

- [ ] **Step 2: 在 ChatPanel 中调用 loadHistory**

在 `ChatPanel.tsx` 中添加 useEffect，组件挂载时加载历史：

```typescript
useEffect(() => {
  void sendMessage; // 引用避免 lint 警告
  // 实际调用 store 的 loadHistory
  const load = async () => {
    const store = useChatStoreV2.getState();
    if (store.messages.length === 0) {
      await store.loadHistory(workspaceId);
    }
  };
  void load();
}, [workspaceId]);
```

注意：这里直接用 `useChatStoreV2.getState()` 避免在 effect 里订阅 store。

- [ ] **Step 3: 修改 sendMessage 中 ensure_thread 的返回处理**

在 `chat-store.ts` 的 `sendMessage` 中，`ensure_thread` 调用后，如果 store 消息为空，将返回的 messages 加载：

```typescript
// After threadRes
const thread = await threadRes.json();
const threadId = thread.id;

// Load existing messages if store is empty (first call after page load)
if (get().messages.length === 0 && thread.messages?.length > 0) {
  const loaded: Message[] = thread.messages.map((m: Record<string, unknown>) => ({
    id: (m.id as string) || crypto.randomUUID(),
    role: (m.role as "user" | "assistant" | "system") || "assistant",
    blocks: Array.isArray(m.blocks) ? m.blocks : [{ kind: "text" as const, content: String(m.content || "") }],
    createdAt: (m.created_at as string) || new Date().toISOString(),
  }));
  set({ messages: loaded });
}
```

- [ ] **Step 4: Run typecheck**

Run: `cd /Users/ze/wenjin/frontend && npm run typecheck`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/stores/chat-store.ts frontend/app/\(workbench\)/workspaces/\[id\]/v2/components/ChatPanel.tsx
git commit -m "feat: load chat history from backend on workspace enter"
```

---

### Task 2: Markdown 渲染（I2）

**Files:**
- Modify: `frontend/app/(workbench)/workspaces/[id]/v2/components/MessageBlock.tsx`

- [ ] **Step 1: 添加 ReactMarkdown 导入**

在 MessageBlock.tsx 顶部添加：

```typescript
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
```

- [ ] **Step 2: 替换 text block 渲染**

将 text block 的渲染从：

```tsx
case "text":
  return (
    <span style={{ whiteSpace: "pre-wrap" }}>
      {block.content}
    </span>
  );
```

替换为：

```tsx
case "text":
  return (
    <div className="prose-chat">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>
        {block.content}
      </ReactMarkdown>
    </div>
  );
```

- [ ] **Step 3: 添加 Markdown 样式**

在 `frontend/app/globals.css` 的 v2 tokens 区域后添加 chat markdown 样式：

```css
/* Chat markdown — minimal v2 styling */
.prose-chat {
  font-size: 13.5px;
  line-height: 1.55;
  color: var(--v2-text-primary);
  font-family: var(--v2-font-sans);
}
.prose-chat p {
  margin: 0 0 8px;
}
.prose-chat p:last-child {
  margin-bottom: 0;
}
.prose-chat strong {
  font-weight: 600;
}
.prose-chat em {
  font-style: italic;
}
.prose-chat ul, .prose-chat ol {
  margin: 4px 0 8px 20px;
  padding: 0;
}
.prose-chat li {
  margin: 2px 0;
}
.prose-chat code {
  font-family: var(--v2-font-mono);
  font-size: 12px;
  background: var(--v2-surface-soft);
  padding: 1px 4px;
  border-radius: 3px;
}
.prose-chat pre {
  background: var(--v2-surface-soft);
  border-radius: var(--v2-radius-md);
  padding: 10px 12px;
  overflow-x: auto;
  margin: 8px 0;
}
.prose-chat pre code {
  background: none;
  padding: 0;
}
.prose-chat h1, .prose-chat h2, .prose-chat h3 {
  font-weight: 600;
  margin: 12px 0 6px;
}
.prose-chat h1 { font-size: 16px; }
.prose-chat h2 { font-size: 15px; }
.prose-chat h3 { font-size: 14px; }
.prose-chat blockquote {
  border-left: 3px solid var(--v2-accent-purple-300);
  margin: 8px 0;
  padding-left: 10px;
  color: var(--v2-text-secondary);
}
.prose-chat a {
  color: var(--v2-accent-purple-700);
  text-decoration: none;
}
.prose-chat a:hover {
  text-decoration: underline;
}
.prose-chat table {
  border-collapse: collapse;
  margin: 8px 0;
  font-size: 12.5px;
}
.prose-chat th, .prose-chat td {
  border: 1px solid var(--v2-border-default);
  padding: 4px 8px;
  text-align: left;
}
.prose-chat th {
  background: var(--v2-surface-soft);
  font-weight: 600;
}
```

- [ ] **Step 4: Run typecheck**

Run: `cd /Users/ze/wenjin/frontend && npm run typecheck`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/app/\(workbench\)/workspaces/\[id\]/v2/components/MessageBlock.tsx frontend/app/globals.css
git commit -m "feat: render chat text blocks with react-markdown"
```

---

### Task 3: 多行输入框（I3）

**Files:**
- Modify: `frontend/app/(workbench)/workspaces/[id]/v2/components/ChatPanel.tsx`

- [ ] **Step 1: 替换 input 为 textarea**

将 `<input>` 元素替换为 `<textarea>`。修改 ChatPanel.tsx：

```tsx
<textarea
  placeholder={isSending ? "等待回复中..." : "输入消息...\nShift+Enter 换行"}
  value={inputValue}
  onChange={(e) => setInputValue(e.target.value)}
  onKeyDown={handleKeyDown}
  rows={1}
  style={{
    flex: 1,
    padding: "8px 12px",
    borderRadius: "var(--v2-radius-md)",
    border: "1px solid var(--v2-border-default)",
    background: "var(--v2-surface-soft)",
    fontSize: 13.5,
    outline: "none",
    fontFamily: "var(--v2-font-sans)",
    color: "var(--v2-text-primary)",
    opacity: isSending ? 0.6 : 1,
    resize: "none",
    minHeight: 38,
    maxHeight: 120,
    lineHeight: "1.4",
  }}
/>
```

- [ ] **Step 2: 修改 handleKeyDown 支持 Shift+Enter**

当前 `handleKeyDown` 在 Enter 时发送。修改为 Shift+Enter 换行、Enter 发送：

```typescript
function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    handleSubmit();
  }
}
```

（当前逻辑已经是这样，只需确认 textarea 的 keydown 行为一致。）

- [ ] **Step 3: 添加 textarea 自动增高逻辑**

添加一个 ref + effect 让 textarea 根据内容自动调整高度：

```typescript
const textareaRef = useRef<HTMLTextAreaElement>(null);

// Auto-resize textarea
useEffect(() => {
  const el = textareaRef.current;
  if (el) {
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 120) + "px";
  }
}, [inputValue]);
```

将 `ref={textareaRef}` 加到 textarea 元素上。

- [ ] **Step 4: Run typecheck + Commit**

Run: `cd /Users/ze/wenjin/frontend && npm run typecheck`

```bash
git add frontend/app/\(workbench\)/workspaces/\[id\]/v2/components/ChatPanel.tsx
git commit -m "feat: replace chat input with auto-resizing textarea"
```

---

### Task 4: 文件上传按钮（I1）

**Files:**
- Create: `frontend/app/(workbench)/workspaces/[id]/v2/components/FileAttachButton.tsx`
- Modify: `frontend/app/(workbench)/workspaces/[id]/v2/components/ChatPanel.tsx`
- Modify: `frontend/stores/chat-store.ts`

- [ ] **Step 1: 创建 FileAttachButton 组件**

```tsx
"use client";

import { useRef, useState } from "react";
import { uploadThreadFiles } from "@/lib/api/threads";

interface FileAttachButtonProps {
  threadId: string | null;
  onAttached: (files: Array<{ name: string; path: string }>) => void;
  disabled?: boolean;
}

export function FileAttachButton({ threadId, onAttached, disabled }: FileAttachButtonProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);

  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const files = e.target.files;
    if (!files?.length || !threadId) return;

    setUploading(true);
    try {
      const result = await uploadThreadFiles(threadId, Array.from(files));
      const attachments = (result.files ?? []).map((f: Record<string, string>) => ({
        name: f.name ?? f.original_name ?? "file",
        path: f.path ?? "",
      }));
      onAttached(attachments);
    } catch {
      // 静默失败
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  return (
    <>
      <input
        ref={inputRef}
        type="file"
        multiple
        style={{ display: "none" }}
        onChange={handleFileChange}
      />
      <button
        onClick={() => inputRef.current?.click()}
        disabled={disabled || uploading || !threadId}
        title="添加附件"
        style={{
          padding: "6px 8px",
          borderRadius: "var(--v2-radius-md)",
          border: "none",
          background: "transparent",
          color: "var(--v2-text-tertiary)",
          fontSize: 18,
          cursor: disabled || uploading ? "not-allowed" : "pointer",
          fontFamily: "var(--v2-font-sans)",
          opacity: disabled || uploading || !threadId ? 0.4 : 1,
          lineHeight: 1,
          display: "flex",
          alignItems: "center",
        }}
      >
        +
      </button>
    </>
  );
}
```

- [ ] **Step 2: 在 ChatPanel 中添加 attachment state 和 FileAttachButton**

在 ChatPanel 中添加：

```typescript
const [attachments, setAttachments] = useState<Array<{ name: string; path: string }>>([]);
const [threadId, setThreadId] = useState<string | null>(null);
```

在 input area 的 `<div>` flex 容器内，textarea 之前加 FileAttachButton：

```tsx
<FileAttachButton
  threadId={threadId}
  onAttached={(files) => setAttachments((prev) => [...prev, ...files])}
  disabled={isSending}
/>
```

- [ ] **Step 3: 在 sendMessage 中传递 attachments**

修改 `handleSubmit` 将 attachments 传入 sendMessage：

```typescript
function handleSubmit() {
  const trimmed = inputValue.trim();
  if (!trimmed || isSending) return;
  setInputValue("");
  const currentAttachments = [...attachments];
  setAttachments([]);
  void sendMessage(workspaceId, trimmed, currentAttachments);
}
```

修改 `chat-store.ts` 的 `sendMessage` 签名和 body：

```typescript
async sendMessage(workspaceId: string, content: string, attachments: Array<{ name: string; path: string }> = []) {
```

在 run/stream 的 body 中加入 attachments：

```typescript
body: JSON.stringify({
  message: content,
  workspace_id: workspaceId,
  attachments: attachments.map((a) => ({
    name: a.name,
    path: a.path,
    kind: "transient",
  })),
}),
```

- [ ] **Step 4: 在 ensure_thread 成功后缓存 threadId**

在 ChatPanel 的 `loadHistory` effect 中，获取到 thread 后设置 threadId：

```typescript
useEffect(() => {
  const load = async () => {
    const store = useChatStoreV2.getState();
    if (store.messages.length === 0) {
      const tid = await store.loadHistory(workspaceId);
      if (tid) setThreadId(tid);
    }
  };
  void load();
}, [workspaceId]);
```

`loadHistory` 返回 threadId。

- [ ] **Step 5: Run typecheck + Commit**

```bash
git add frontend/app/\(workbench\)/workspaces/\[id\]/v2/components/FileAttachButton.tsx frontend/app/\(workbench\)/workspaces/\[id\]/v2/components/ChatPanel.tsx frontend/stores/chat-store.ts
git commit -m "feat: add file upload button to chat input"
```

---

### Task 5: Thinking 内容过滤（I5）

**Files:**
- Modify: `frontend/app/(workbench)/workspaces/[id]/v2/components/ThinkingBlock.tsx`

- [ ] **Step 1: 添加内容过滤函数**

在 ThinkingBlock.tsx 中添加过滤函数，移除模型自我声明：

```typescript
function filterThinkingContent(content: string): string {
  // 过滤模型自我声明（"我是 MiMo"、"我是 GPT"、"由...开发" 等模式）
  const lines = content.split("\n");
  const filtered = lines.filter(
    (line) =>
      !/^(我是|I am|I'm)\s.*(MiMo|GPT|Claude|ChatGPT|助手|模型)/i.test(line.trim()) &&
      !/由.{2,10}(团队|公司|开发)/.test(line.trim()) &&
      !/虽然我自己/.test(line.trim()),
  );
  return filtered.join("\n").trim();
}
```

- [ ] **Step 2: 应用过滤**

在渲染 thinking 内容时应用过滤：

```tsx
const filtered = filterThinkingContent(block.content);
if (!filtered) return null;
// 渲染 filtered 而非 block.content
```

- [ ] **Step 3: Run typecheck + Commit**

```bash
git add frontend/app/\(workbench\)/workspaces/\[id\]/v2/components/ThinkingBlock.tsx
git commit -m "fix: filter model self-identification from thinking blocks"
```

---

### Task 6: 端到端验证

- [ ] **Step 1: Run typecheck**

Run: `cd /Users/ze/wenjin/frontend && npm run typecheck`
Expected: PASS

- [ ] **Step 2: Rebuild backend + frontend**

```bash
cd /Users/ze/wenjin && docker compose up -d --build worker gateway
```

- [ ] **Step 3: 功能验证清单**

打开 workspace v2 页面，验证：

1. **历史加载**: 进入已有对话的 workspace，看到之前的消息
2. **Markdown**: 发一条消息，确认回复中的标题、列表、粗体、代码块正确渲染
3. **多行输入**: Shift+Enter 可以换行，Enter 发送
4. **文件上传**: 点击 `+` 按钮，选择文件，发送带附件的消息
5. **Thinking**: 回复的思考过程中不包含 "我是 MiMo" 等自我声明
6. **发送后可输入**: 第一条消息发送后输入框仍可编辑

- [ ] **Step 4: 最终 commit（如有修复）**

```bash
git add -A
git commit -m "fix: chat pipeline end-to-end fixes"
```
