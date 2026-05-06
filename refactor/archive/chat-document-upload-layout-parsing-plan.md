# Chat 文档上传与 Layout Parsing 中间件收敛计划

## 目标

把 chat 链路的文档上传做成一条稳定、可观测、可扩展的基础能力：

- 用户在 chat 输入框内可以直接上传 PDF / 图片，并在发送消息时附带到当前 thread。
- 上传后的 PDF / 图片自动调用 layout parsing 服务，产出 Markdown、图片资源和 manifest。
- Agent 侧通过统一中间件拿到上传文件、解析状态、可读 Markdown 路径和必要摘要，而不是各业务 feature 自己重复解析。
- 服务配置走环境变量 / secret，不把 API URL 或 TOKEN 写入仓库。
- 解析失败不阻塞 chat，失败信息进入附件 metadata，Agent 仍能看到原始文件路径。

## 现状判断

项目里已经存在一部分能力，不需要从零实现：

- 前端 `WorkspaceThreadComposer` 已有“添加附件”按钮、上传归类选择、pending attachment 列表。
- 前端 `ThreadPanel` 已经会在发送消息前 `ensureWorkspaceThread()`，然后调用 `uploadThreadFiles()` 上传附件。
- 后端 `/threads/{thread_id}/uploads` 已经保存 thread-scoped 上传文件，并能按 `literature` / `workspace_context` / `transient` 三类处理。
- 后端 `UploadPreprocessor` 已经实现 layout-parsing API 调用，包含 base64 文件上传、`fileType` 推断、Markdown 落盘、图片落盘、manifest 输出、SSRF 防护、远程图片大小限制。
- 后端 `UploadsMiddleware` 已经会把当前消息附件和历史附件注入 `<uploaded_files>`，并读取 `metadata.preprocess.markdown_paths` / `manifest_path` 暴露给 Agent。

因此本轮不是新增一套“上传系统”，而是把已有上传和解析链路正式收敛成 SSOT，并补齐 UI、配置、异步状态、服务兼容性和测试。

## 目标架构

### 责任边界

- `LayoutParsingSettings`：layout parsing Provider 配置 SSOT，只从环境变量读取。
- `UploadPreprocessor`：唯一负责调用外部 layout parsing 服务、落盘 Markdown / images / manifest 的服务。
- `/threads/{thread_id}/uploads`：HTTP adapter，只负责鉴权、保存文件、调用或调度 preprocess、返回 attachment metadata。
- `UploadsMiddleware`：Agent 上下文 presenter，只消费 attachment metadata 和 manifest，不直接持有密钥，不重复实现 Provider 调用。
- `ThreadPanel` / `WorkspaceThreadComposer`：用户上传入口和上传状态展示，不直接知道 layout parsing 服务细节。

### 推荐数据流

1. 用户在 chat 输入框点击“上传文档”。
2. 前端选择 PDF / 图片，生成 pending attachment。
3. 发送消息前，前端确保 workspace thread 存在。
4. 前端调用 `/threads/{thread_id}/uploads` 上传文件。
5. 后端保存原始文件到 `/mnt/user-data/uploads/{filename}`。
6. 后端调用或调度 `UploadPreprocessor`。
7. `UploadPreprocessor` 调用 layout parsing 服务，生成：
   - `doc_{n}.md`
   - markdown 引用图片
   - 可视化 / 输出图片
   - `manifest.json`
8. 后端把 preprocess 结果写入 attachment metadata：
   - `metadata.preprocess.status`
   - `metadata.preprocess.provider`
   - `metadata.preprocess.file_type`
   - `metadata.preprocess.markdown_paths`
   - `metadata.preprocess.markdown_image_paths`
   - `metadata.preprocess.output_image_paths`
   - `metadata.preprocess.manifest_path`
   - `metadata.preprocess.error`
9. 用户消息持久化时携带 attachments metadata。
10. `ThreadTurnHandler` 构建 `uploaded_files` state。
11. `UploadsMiddleware` 注入 `<uploaded_files>`，告诉 Agent 原始文件路径、解析状态、Markdown 路径、manifest 路径。
12. Agent 需要读取正文时，通过 `read_file` 读取 Markdown，而不是直接解析 PDF。

## 安全与配置要求

不能把用户提供的 TOKEN 写入代码或计划中的可执行配置。落地时使用：

```bash
LAYOUT_PARSING_ENABLED=true
LAYOUT_PARSING_API_URL=https://.../layout-parsing
LAYOUT_PARSING_TOKEN=...
LAYOUT_PARSING_TIMEOUT_SECONDS=120
LAYOUT_PARSING_USE_DOC_ORIENTATION_CLASSIFY=false
LAYOUT_PARSING_USE_DOC_UNWARPING=false
LAYOUT_PARSING_USE_CHART_RECOGNITION=false
```

补充要求：

- 已在对话中出现过的 token 应按泄露处理，生产使用前建议轮换。
- `.env.example` 只写变量名和占位值，不写真实 token。
- 后端日志不得打印 token、完整 Authorization header、base64 文件内容。
- 远程图片下载必须继续保留 SSRF 防护、大小限制、scheme 限制和私网 IP 拦截。
- 对解析结果里的相对路径继续做 path traversal 防护。

## 需要改进的关键点

### 1. 前端上传入口 UX 收敛

现状已经有“添加附件”按钮，但入口偏工程化。目标是让 chat 对话框内的文档上传能力更明确。

计划：

- 把上传按钮视觉上并入输入框 toolbar，命名为“上传文档”或“添加资料”。
- `input[type=file]` 增加 `accept=".pdf,image/*"`，先只支持 layout parsing 可处理的 PDF / 图片。
- pending attachment 展示解析目标：
  - PDF / image：显示“发送后自动解析为 Markdown”
  - 其他类型：显示“不解析，仅作为附件”
- 允许“只有附件无文本”时发送，自动使用默认消息，例如“请阅读这些附件，并结合上下文继续分析。”；如果不做该能力，至少文案要说明必须补一句说明。
- 对上传分类做降噪：
  - 默认 `transient`
  - 分类选择可折叠到高级选项
  - 不要让普通用户一开始理解 `literature` / `workspace_context` / `transient` 的系统含义
- 文件上传后，在消息卡片里展示 preprocess 状态：
  - `succeeded`：已解析
  - `failed`：解析失败，可继续使用原文件
  - `disabled`：解析服务未启用
  - `skipped`：文件类型不支持解析

### 2. Layout Parsing Provider 兼容性补齐

用户提供的 PaddleOCR / AIStudio 示例和当前实现基本一致，但响应里的图片字段存在两种可能：

- 示例代码把 `markdown.images` / `outputImages` 当 URL 下载。
- 文档说明里又提到图像可能是 JPEG base64 编码。

计划：

- `UploadPreprocessor` 同时支持 URL、data URL、裸 base64 三种图片返回格式。
- `markdown.images` 保留服务返回的相对路径，但必须继续做安全路径归一化。
- `outputImages` 的文件名继续 sanitize。
- manifest 增加原始 provider 响应摘要：
  - `log_id`
  - `page_count`
  - `result_count`
  - `provider_options`
  - `created_at`
- payload 参数从 `LayoutParsingSettings` 生成，避免散落在服务内部。
- 扩展配置项以覆盖常用参数：
  - `use_layout_detection`
  - `layout_threshold`
  - `layout_nms`
  - `restructure_pages`
  - `merge_tables`
  - `relevel_titles`
  - `prettify_markdown`
  - `visualize`
- 对 4xx / 5xx / 非标准 JSON 做明确错误分类，写入 `preprocess.error`。

### 3. 中间件职责收敛

不要让 `before_model` 每次模型调用都发起外部解析请求。原因：

- 会把模型响应路径变成外部 OCR 服务强依赖。
- 容易重复调用，产生费用和延迟。
- middleware 通常应该是上下文组装和状态修正，不适合做重 IO 副作用。

推荐方案：

- 解析仍在 upload ingestion 阶段完成，或通过后台任务异步完成。
- `UploadsMiddleware` 只消费解析结果并注入上下文。
- 如果必须“middleware 触发解析”，也应做成幂等调度：
  - 检查 attachment metadata 没有 preprocess 结果。
  - 写入 `preprocess.status=pending`。
  - 调度后台任务。
  - 当前 turn 不阻塞模型，只提示“解析中，可先基于原始文件继续”。

中间件计划改造：

- 保留 `UploadsMiddleware` 名称，避免大面积迁移。
- 内部拆出 `UploadContextPresenter` 或私有纯函数，专门负责从 attachment metadata 渲染 `<uploaded_files>`。
- 注入内容增加 Markdown 摘要，但严格限长：
  - 每个文件最多展示前 1200-2000 chars 的 Markdown excerpt。
  - 完整内容仍通过 `read_file` 读取。
- manifest 和 markdown 路径作为 SSOT，不把大段全文塞进 prompt。
- 对历史附件只展示最近 N 个或当前 thread 相关附件，避免 prompt 被长期历史上传污染。

### 4. 异步解析与状态更新

当前上传 endpoint 同步 preprocess 的好处是简单，但 PDF 较大时会阻塞发送链路。

推荐分两档：

- 小文件 / 图片：允许同步解析，设置短超时。
- 大 PDF：调度后台任务，上传接口立即返回 `preprocess.status=pending`。

需要补齐：

- `ThreadService` 增加或复用 attachment metadata 更新方法，支持更新 `metadata.preprocess`。
- 解析任务完成后发布 workspace/thread event，让前端刷新消息里的附件状态。
- 前端 store 已有 attachment extraction 状态合并逻辑，可复用并扩展到 preprocess。
- 如果用户在解析未完成时立刻发送消息，Agent 看到 `pending`，并可提示稍后重试或先基于文件名/原始路径处理。

### 5. Workspace 知识沉淀

`workspace_context` 上传现在会创建 artifact 和 knowledge。计划让解析结果成为该知识沉淀的优先来源。

计划：

- 如果 preprocess succeeded，artifact 的 `content.text_preview` 优先使用 Markdown 前 N 字。
- artifact content 增加：
  - `preprocess_manifest_path`
  - `preprocessed_markdown_paths`
  - `preprocess_status`
- memory / knowledge 写入时使用 Markdown 摘要，不再只依赖轻量 `extract_document_preview()`。
- `literature` 上传仍保留 paper extraction 任务，layout markdown 可作为补充输入，不替代文献元数据抽取。

### 6. Chat 使用链路

最终用户链路应该是：

1. 用户点 chat 输入框内上传按钮。
2. 选择 PDF 或图片。
3. 附件 chip 出现在输入框上方。
4. 用户输入“帮我总结这份材料”或直接发送默认附件消息。
5. 系统上传文件并启动解析。
6. 用户消息显示附件卡片。
7. 如果解析已完成，Agent 在当前回复里可以读取 Markdown。
8. 如果解析未完成，Agent 明确说明解析中，不假装已读。
9. 解析完成后，附件状态更新为“已解析”，后续 turn 可直接引用 Markdown。

## 推荐实施顺序

### Phase 0：配置与密钥收敛

- 确认生产 / 测试环境配置 `LAYOUT_PARSING_*`。
- `.env.example` 增加变量说明。
- 不提交真实 token。
- 对已暴露 token 做轮换。

验收：

- 本地不配置 token 时，上传 PDF 返回 `preprocess.status=disabled`，不报 500。
- 配置 token 后，服务可以调用 layout parsing。

### Phase 1：Provider 输出兼容与 manifest 增强

- 支持 URL / data URL / base64 图片返回。
- manifest 增加 `log_id`、provider options、result count、created_at。
- 增加配置项覆盖更多 PaddleOCR 参数。

验收：

- mock URL 图片可落盘。
- mock base64 图片可落盘。
- 异常响应写入 `status=failed` 和清晰 error。
- 不出现 path traversal。

### Phase 2：中间件上下文增强

- `UploadsMiddleware` 继续作为统一入口。
- 注入 preprocess manifest、markdown paths、有限 excerpt。
- 历史附件做数量限制。
- 明确提示 Agent：完整内容读 markdown 文件，不要直接臆测 PDF 内容。

验收：

- 当前 turn 上传 PDF 后，prompt 中包含 `<uploaded_files>`、解析状态和 Markdown 路径。
- Markdown excerpt 限长。
- 解析失败时仍包含原始文件路径和失败原因。

### Phase 3：前端 chat 上传体验优化

- 把按钮收敛到输入框工具栏。
- 增加 `accept=".pdf,image/*"`。
- 增加 pending / succeeded / failed / disabled / skipped 状态展示。
- 支持附件-only 默认消息，或明确禁止并给出文案。

验收：

- 用户可以在 chat 面板直接上传 PDF / 图片。
- 上传后附件卡片能显示解析状态。
- 不支持类型不会误导成“已解析”。

### Phase 4：异步解析

- 大 PDF 走后台任务。
- upload endpoint 返回 pending metadata。
- 任务完成后更新 thread message attachment metadata。
- 前端通过 event / refresh 合并状态。

验收：

- 大文件上传不长时间卡住 composer。
- pending 状态可更新为 succeeded / failed。
- 用户无需刷新页面即可看到附件解析状态变化。

### Phase 5：Workspace 知识沉淀

- `workspace_context` artifact 使用 Markdown 预览。
- knowledge 写入引用 Markdown 摘要。
- literature 上传保留 paper extraction，同时记录 layout parsing 结果路径。

验收：

- KnowledgeRail / artifacts 能看到由上传上下文沉淀的资料。
- Agent 后续 turn 可以复用已解析 Markdown。

## 测试计划

后端：

- `UploadPreprocessor`
  - unsupported 文件 skipped
  - PDF fileType=0
  - image fileType=1
  - URL 图片落盘
  - base64 图片落盘
  - data URL 图片落盘
  - path traversal 图片路径被拒绝或改名
  - provider 4xx / 5xx 转 failed metadata
  - response missing result 转 failed metadata
- `uploads` router
  - transient 上传写 thread path 和 preprocess metadata
  - workspace_context 上传写 artifact / knowledge / preprocess metadata
  - literature 非 PDF 拒绝
  - layout parsing disabled 不阻塞上传
- `UploadsMiddleware`
  - 注入当前附件
  - 注入 preprocess markdown paths / manifest
  - 注入 excerpt 限长
  - historical attachment 限制数量

前端：

- `uploadThreadFiles()` multipart payload。
- `ThreadPanel` 附件上传后随消息发送。
- `WorkspaceThreadComposer` 显示上传按钮、pending attachment、状态 chip。
- 附件-only 行为。
- 解析状态更新合并到 message metadata。

集成：

- 上传 PDF，mock layout parsing 返回 Markdown，Agent prompt 中出现 Markdown 路径。
- 上传图片，mock layout parsing 返回 Markdown 和 output image。
- provider 失败时，chat 仍能发送，附件显示失败状态。

## 风险与决策

- 不建议把真实 provider 调用放进 `before_model` 同步执行。应把 middleware 定位为“消费解析结果并注入上下文”，解析副作用在上传阶段或后台任务中完成。
- 用户给出的示例 token 已出现在对话中，应视为不适合长期生产使用。
- layout parsing 对大 PDF 有页数和耗时风险，必须有超时、大小限制和异步路径。
- PaddleOCR 文档对图片字段返回 URL 还是 base64 的描述不完全一致，必须两种都兼容。
- Markdown 全文直接塞进 prompt 会造成 token 膨胀，应该只注入 excerpt 和路径。

## 完成定义

- Chat 面板中用户可以明确上传 PDF / 图片。
- 上传后自动解析，解析结果作为 attachment metadata 和 manifest 持久化。
- Agent 通过 `UploadsMiddleware` 稳定看到解析状态和 Markdown 路径。
- 配置和 token 完全走环境变量。
- 外部服务失败不阻断 chat。
- 后端 / 前端测试覆盖上传、解析、middleware 注入和失败降级。
