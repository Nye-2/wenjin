# Migration Phase Review

更新时间: 2026-03-26
适用项目: `wenjin`
对照项目: `deer-flow`
状态: Current Round Completed

## 1. 用户确认过的设计约束

本轮 review 和修复以以下约束为准:

- 保留视觉能力，不回退。
- chat 链路必须支持直接文件上传。
- 上传分类由用户显式选择，不做隐式猜测。
- `literature` 进入文献中心。
- `workspace_context` 进入 workspace 上下文和记忆。
- `transient` 只作为当前对话附件，不做额外沉淀。
- chat 返回需要支持文本 + 结构化卡片/文件/artifact + 跳转动作。
- 保留 Docker sandbox，且近期必须作为真实可用能力。
- 记忆系统继续保持 DB-native，而不是回退到文件态。
- 超级智能体方向采用 `feature-first + lightweight-skill`，不做 deer-flow runtime 的整仓直搬。

## 2. 能力迁移矩阵

| 能力域 | deer-flow | 当前项目状态 | 结论 |
|---|---|---|---|
| Thread sandbox / uploads / outputs 线程隔离 | 完整 | 已完成 | 已迁移并结合 workspace 语义增强 |
| Chat 直接上传文件 | 完整 | 已完成 | 已补齐，请求契约、上传路由、UI、附件卡片均已接通 |
| Vision / `view_image` | 完整 | 已完成 | 已恢复 |
| Artifact / 文件呈现 | 完整 | 已完成 | 已支持结构化 blocks + artifact metadata |
| 文献上传后自动抽取 | deer-flow 无此学术特化 | 已完成 | 当前项目更强 |
| Workspace canonical file URL / serve | deer-flow 为 thread artifacts | 已完成 | 当前项目更强 |
| DB-native memory | deer-flow 以事实注入为主 | 已完成 | 当前项目坚持 DB-native |
| Memory contextual recall | deer-flow 有多轮上下文 + 相关度选择 | 本轮补齐 | 由“按 confidence 注入”升级为“上下文相关排序 + 精确 token 预算” |
| Memory capture from chat | deer-flow 可持续沉淀 | 本轮补齐 | 之前 chat 路径只注入不回写，现已修复 |
| Tool-level execution middleware | deer-flow 有较完整 tool runtime | 本轮补齐 | 之前 `ExecutionMiddleware` 存在但未真正生效 |
| Lead agent execution tools | 可调用 | 本轮补齐 | 仅对 lead agent 暴露，避免污染未接 middleware 的 subagent 路径 |
| Docker sandbox as usable runtime | 完整 | 基本完成 | provider 已可切换，仍需更多真实 E2E 验证 |
| 子代理执行能力 | 有 | 本轮补齐 | subagent graph / executor / task tool / API 默认配置已统一接入 `DynamicToolNode` + execution middleware |
| Office/PDF 自动转 markdown | deer-flow 有 | 未迁移 | 当前只做 preview 提取，不做完整文档转 markdown |
| 全 workspace feature parity | deer-flow 无 academic workspace 体系 | 部分 | thesis 最完整，其余 workspace 仍需继续补齐 |

## 3. Phase 0: Gap Mapping

目标:

- 明确哪些能力已迁移、哪些能力只是“代码存在但未接线”、哪些能力仍未迁移。

发现:

1. `ExecutionMiddleware` 已实现，但 `build_pipeline()` 没有注册。
2. lead agent 运行时只跑 `before_model/after_model`，`before_tool/after_tool` 根本没有执行入口。
3. `compile_latex_tool` 已存在，但 lead agent 工具清单没有暴露它。
4. chat memory path 默认没有 capture，导致“记忆系统只有注入，没有持续沉淀”。
5. 当前 memory 注入预算仍是 `max_tokens * 4` 粗估，且 facts 仍按 confidence 为主，不是按当前对话相关性选取。

阶段性 review:

- Start Review:
  已确认用户约束和能力边界，避免误把项目拉回 deer-flow 原 runtime。
- Mid-Phase Review:
  识别出“存在代码不等于存在能力”，特别是 execution 和 memory 两条链都存在半接线状态。
- Exit Review:
  P0 结论已明确，后续修复优先级为: `execution tool runtime` > `memory capture/retrieval` > `feature parity/backlog`。

## 4. Phase 1: Chat -> Task -> Result Mainline Review

目标:

- 复核 chat、task、artifact、workspace 回写的一致性。

本轮确认:

1. chat 直接上传、附件卡片、文献抽取状态同步、workspace 文件 URL 等核心链路已落地。
2. 论文上传后的抽取任务状态能回写到 thread attachment metadata，并能在前端实时同步。
3. 结构化回复 block / artifact contract 已形成基础事实源。

仍存风险:

1. branch thread / main thread 的恢复和体验仍有继续收敛空间。
2. feature parity 在 thesis 外仍不均衡，属于后续 phase 的重点。

阶段性 review:

- Start Review:
  chat 已不再只是消息面板，而是统一入口。
- Mid-Phase Review:
  主链最明显的断点不在 chat/task，而是在 tool runtime 和 memory runtime。
- Exit Review:
  本阶段没有新增主链 bug 发现，继续把精力投入 execution 和 memory 两个共性底层能力。

## 5. Phase 2: Execution / Sandbox Closure

目标:

- 把执行能力从“概念存在”修成“lead agent 真能用”。

已落地修复:

1. `DynamicToolNode` 新增 tool 级 middleware hook，真实执行 `before_tool/after_tool`。
2. 每个 tool call 使用独立 runtime config，避免 middleware 结果在并发 tool call 下互相污染。
3. `build_pipeline()` 现在会尝试注册 `ExecutionMiddleware`。
4. `ExecutionMiddleware` 支持从 `paper_service.db` 补 BibTeX，不再依赖外部手塞 `db`。
5. lead agent 现在按 middleware 实际能力决定是否暴露 execution tools。
6. `compile_latex_tool` 仅对已接 tool middleware 的 lead agent 暴露，避免把 subagent 路径带坏。

阶段性 review:

- Start Review:
  原问题不是单点遗漏，而是“tool middleware 整体未接入”。
- Mid-Phase Review:
  修复方案改为从 `DynamicToolNode` 层接通，而不是只在 pipeline 里 append middleware。
- Exit Review:
  执行能力已从 dead code 状态转为可用状态，但当前 agent 暴露的 execution tool 仍以 LaTeX 为主，后续可继续扩展图表/图像等能力。

## 6. Phase 3: Memory Runtime Closure

目标:

- 把记忆系统从“半条链”修成“可注入、可回写、可按上下文取用”。

已落地修复:

1. `MemoryMiddleware` 在 memory enabled 时默认开启 capture，不再要求调用方必须显式传 queue。
2. `MemoryMiddleware.before_model()` 会基于最近多轮真实对话生成 `current_context`，并传给 memory 选择逻辑。
3. memory prompt 预算改为使用 `tiktoken` 精确计数，而不是 `max_tokens * 4` 粗估。
4. memory 召回增加轻量上下文相关性排序:
   workspace match + lexical similarity + confidence 共同决定注入顺序。
5. memory config 增加:
   `max_context_turns` / `similarity_weight` / `confidence_weight`。
6. memory debug API 同步暴露新的 runtime config。

阶段性 review:

- Start Review:
  原实现更接近“静态 facts 注入”，不是 deer-flow 后期那种基于上下文的动态选择。
- Mid-Phase Review:
  选择保持 DB-native，不引入新的文件态 memory，也不强行把完整 deer-flow TF-IDF 实现生搬过来。
- Exit Review:
  当前方案已补上最关键的运行时缺口；后续若需要更高召回精度，可继续升级为 TF-IDF 或 embedding rerank。

## 7. Phase 4: Subagent Runtime Closure

目标:

- 让 subagent 路径不再绕开 lead-agent 已经补齐的 tool runtime。

已落地修复:

1. subagent graph 统一切到 `DynamicToolNode`，并按运行时能力自动接入 `ExecutionMiddleware`。
2. `SubagentExecutor` 现在透传 `thread_id` / `workspace_id` / `user_id` / `model_name`，与主链 runtime config 保持一致。
3. `task` delegation tool 生成 subagent 时默认携带 execution-capable tools，并显式关闭递归 subagent 暴露。
4. `/subagents` API 的默认 manager 配置同样改为 execution-capable tool 集合。
5. `GlobalSubagentManager` 不再忽略任务级 `system_prompt/tools`，学术子代理配置会真实进入执行图，而不是只停留在 API payload。
6. 针对子代理 runtime 增补了 execution smoke、graph/tool wiring、manager context forwarding 等 focused tests。

阶段性 review:

- Start Review:
  原问题不是“子代理少几个工具”，而是整个 subagent runtime 仍停留在旧的弱执行图。
- Mid-Phase Review:
  修复策略没有回退到 deer-flow 的重 runtime，而是把现有 lightweight-subagent 路径升级到与主链一致的 tool/middleware 机制。
- Exit Review:
  当前 subagent 已与 lead agent 在 execution runtime 上对齐，剩余工作重点转向更真实的 E2E smoke 和 workspace parity，而不是再做基础接线。

## 8. 当前回归结果

已通过 focused 回归:

- `backend/tests/agents/test_lead_agent.py`
- `backend/tests/agents/lead_agent/test_dynamic_tools.py`
- `backend/tests/agents/lead_agent/test_tools.py`
- `backend/tests/agents/test_pipeline_assembly.py`
- `backend/tests/unit/middlewares/test_memory.py`
- `backend/tests/agents/memory/test_memory.py`
- `backend/tests/gateway/routers/test_memory.py`
- `backend/tests/subagents/test_graph.py`
- `backend/tests/subagents/test_graph_academic.py`
- `backend/tests/subagents/test_task_tool.py`
- `backend/tests/subagents/test_executor.py`
- `backend/tests/subagents/test_manager.py`
- `backend/tests/subagents/test_execution_runtime.py`
- `backend/tests/subagents/test_api.py`

本轮新增测试覆盖:

- `DynamicToolNode` tool middleware hook
- execution tool 暴露边界
- pipeline 中 execution / memory capture 装配
- memory 上下文排序
- memory middleware 传递 recent conversation context
- subagent runtime execution wiring
- task-level `system_prompt/tools` 真正进入 subagent graph

全量 backend 回归:

- `2282 passed, 6 skipped in 56.97s`

## 9. 剩余 backlog

P1:

1. 为 execution + docker sandbox 补一条真实端到端 smoke，不只停留在 focused/unit 层。
2. 继续评估 branch thread / main thread 恢复策略。
3. 继续做五类 workspace 的 feature parity review，尤其是 thesis 以外的 service / artifact / chat 闭环。
4. 为 subagent manager / API / sandbox 补更贴近真实业务的 timeout、cancel、artifact writeback E2E。

P2:

1. 评估是否需要恢复 deer-flow 风格的 Office/PDF -> Markdown 完整转换链。
2. 把 memory relevance 从轻量 lexical scoring 继续升级到 TF-IDF 或 embedding rerank。
3. 继续评估 execution tool 面扩展，如图表、代码产物与更丰富的 sandbox artifact 类型。

## 10. 结论

截至 2026-03-26，本轮最关键的三个迁移缺口已经关闭:

1. 执行能力不再是“有中间件、有工具、但实际不会跑”的假接线状态。
2. 记忆系统不再是“只注入、不沉淀、粗预算、弱相关”的半成品状态。
3. 子代理不再是“主链能执行、子链却绕开 execution runtime”的双轨状态。

当前项目与 deer-flow 的关系已经从“骨架迁移后有明显断口”推进到“核心链路可用，但 feature parity 和更深层 E2E 仍需继续补齐”的阶段。
