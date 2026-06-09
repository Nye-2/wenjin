# Workspace 当前状态

更新时间：2026-06-08
状态：Current
适用项目：`wenjin`

本文件是 workspace/thread/capability 执行协作行为的当前事实源。

## 1. 用户入口

1. canonical workspace route：`/workspaces/{workspace_id}`
2. canonical workspace Prism route：`/workspaces/{workspace_id}/prism`
3. capability 入口：通过 chat 面板对话触发，Chat Agent 根据 mission catalog 识别意图后调用 `launch_feature`
4. 旧 `/chat` 语义已收敛到当前 workspace chat / execution 体系，不再作为独立 feature 流程事实源
5. 旧 workspace-owned `/latex/{project_id}` 页面入口已移除；主稿只通过 workspace Prism surface 进入
6. capability 卡片点击只代表“选择能力”；如果没有具体主题、问题、材料、query、keywords、dataset 或 source artifact，系统只返回需要补充上下文的 advisory，不创建执行、不扣积分、不启动外部检索

## 2. 双 Agent 拓扑

1. **Chat Agent**（左面板）：处理对话、意图识别、调度 capability
2. **Lead Agent v2**（右面板）：执行 capability graph，运行 subagent，产出结构化结果
3. 1:1 映射：lead-busy 时阻塞新的 dispatch
4. Chat turn 本身通过 `/api/threads/{thread_id}/runs/stream` 运行；当 Chat Agent 调用 `launch_feature` 时，stream 会显式输出 `tool_invocation` 与 `tool_result`
5. `launch_feature` 的 `tool_result.status == "launched"` 必须包含 canonical `execution_id`，前端据此建立 run receipt 与右侧 Current run 焦点
6. `launch_feature` 的 `tool_result.status == "advisory"` 表示尚未进入执行链路；前端只展示补充信息提示，不设置 active run，也不打开 Current run
7. Chat Agent 不注册 sandbox-backed bash/file tools，不持有 sandbox state，也不通过 middleware acquire sandbox；sandbox 只能在右侧 Lead Agent graph 的 subagent 节点里执行
8. DataService 持久化的 chat block payload 只保留 canonical `kind`；旧 kind/type 输入可被归一化，但不保存 `legacy_kind` 影子字段。

## 3. Capability 数据驱动

1. Capability 定义在 YAML seed 文件（`backend/seed/capabilities/{workspace_type}/`），并由 DataService Catalog 持久化为 SSOT。
2. 当前 capability schema 为 `capability.v2`；旧 workflow-step id 已删除，不提供 alias、fallback 或双读兼容层。
3. Capability Skill 定义在 `backend/seed/skills/`，当前 schema 为 `capability_skill.v2`；skill 是 worker instruction pack，不是用户入口。
4. Catalog skill DB row 必须包含完整 canonical `skill_json`；projection/preload 不从旧字段读时合成 skill pack，缺失时直接失败。
5. 每个 capability 的 `mission` 定义产品目标、主 surface、document role 和允许交付物。
6. 每个 capability 的 `context_policy`、`sandbox_policy`、`review_policy`、`quality_gates` 会进入 Lead Agent v2 `capability_policy`。
7. 每个 capability 的 `graph_template` 定义执行阶段和 subagent task。
8. `OutputMappingResolver` 将 subagent 输出转换为 typed `ResultOutput`；`kind: prism_file_change` 不进入普通 room outputs，而由普通 Lead runtime / TeamKernel 通过共享 Prism staging helper 写入 DB-backed review item。
9. Capability launch context 只能来自用户显式输入、query seed、route params、source artifact 和已提交的 room context；不得用 workspace 名称/描述、capability 名称、通用卡片提示词或“未命名任务”合成 goal。

## 4. User-Facing Workspace Rooms

1. **Library** — 文献条目（library_item outputs commit 到此）
2. **Documents** — 文档（document outputs）
3. **Decisions** — 决策记录（decision outputs）
4. **Memory** — 事实和偏好（memory_fact outputs）；长期记忆读取、提取写入和压缩通过 Knowledge DataService client 完成
5. **Run History** — 执行历史记录
6. **Tasks** — 后续任务（task outputs）
7. **Settings** — 工作区设置

Sandbox 不再是用户可操作 room。Sandbox 是 Lead Agent / subagent 使用的内部执行基座；用户只在 execution/run detail、ResultCard 和 review item 中查看只读计算记录、脚本摘要、日志、产物和 provenance。内部诊断 capability 可以被 Chat Agent 调度，但实际 Docker sandbox 运行必须发生在 LeadAgentRuntime 的 `sandbox_python` subagent 或 Lead/subagent agent harness 中。

当前 sandbox 运行态已收敛为 workspace 级单环境：每个 workspace 最多一个 active sandbox environment，runtime provider key 为 `workspace-{workspace_id}`。Docker container 不跨任务常驻；每次 run 启动短生命周期容器，但挂载同一个 `/workspace`，保留数据集、脚本、outputs、Python venv 和 package cache。`sandbox_python` subagent 只声明 `dependency_hints` 和 Python 脚本，Lead-owned runtime 在 workspace lease 内自动确保 venv、安装依赖、缺包重试一次，并把安装记录为 unbilled `install_dependencies` sandbox job；`sandbox.run_python` 的 `script_name` 在 harness boundary 和 runner 内共用同一 sanitizer，最终只会写入 `/workspace/scripts/{safe_name}`；实际 run job 仍通过 sandbox credit reservation 计费。harness `sandbox.run_python` 每次返回都会附带三类证据：`execution_manifest(schema=wenjin.harness.run_python.execution_manifest.v1)` 是运行身份契约，记录 workspace/execution/node/invocation、脚本路径、dependency hints、job/environment id、网络 profile 和有效 timeout；`reproducibility_manifest(schema=wenjin.harness.run_python.reproducibility_manifest.v1)` 是可复现实验证据契约，记录脚本、requested/installed dependencies、sandbox run/install job、retry count、生成产物、已同步 dataset provenance 和 run/install command audit 的 verdict/risk 摘要；`experiment_narrative(schema=wenjin.harness.run_python.experiment_narrative.v1)` 是长程实验接续契约，记录 status、script path、dataset/artifact paths、dependency names、command risk 和 next actions。manifest / narrative 不包含 raw stdout/stderr、环境变量、API key、host path 或 raw argv。`report_markdown` 会展示用户可读的 Experiment narrative、Reproducibility 和 Dataset provenance 段落，包括脚本路径、依赖、install job ids、retry count、command audit 摘要、dataset manifest path、dataset input paths/source ids/hash 摘要和 reviewable artifact paths；依赖安装失败也会返回带 Recovery guidance 的报告，提示检查 pinned package spec、Python 环境兼容性和需要系统库时的替代方案。用户代码非零退出时，harness tool 会保留 runner output payload 并附加 `failure_classification(schema=wenjin.harness.run_python.failure_classification.v1)` / `error_code=python_exit_nonzero` 和 bounded Recovery guidance，而不是把失败压扁成普通工具异常。

Workspace sandbox 文件系统契约由 `backend/src/sandbox/workspace_layout.py` 统一定义，Local/Docker provider acquire 时创建同一套布局。Agent 可见根目录固定为 `/workspace`：`main` 放主项目文件，`datasets` 放数据集，`scripts` 放实验脚本，`outputs` 放可展示产物，`reports` 放阶段报告，`tmp` 放临时 scratch，`tmp/tasks` 是稳定 task-scoped scratch root，`.wenjin/env` 和 `.wenjin/cache` 由 Lead-owned runtime 管理，`.wenjin/manifest.json` 记录机器可读 layout 契约，整个 `.wenjin/**` 元数据树对 model tools 都是 protected。所有 workspace type 共用同一套目录；垂直差异通过 `workspace_profile(schema=wenjin.workspace_sandbox.type_profile.v1)` 进入 `.wenjin/manifest.json`、DataService sandbox environment metadata 和 harness context，只给 `primary_files`、`script_paths`、`output_paths`、`report_paths` 与规则建议。例如 `sci` 推荐 `/workspace/main/main.tex`、`/workspace/main/refs.bib`、`/workspace/scripts/analysis.py`、`/workspace/outputs/figures` 和 `/workspace/reports/experiment-report.md`；`patent` 推荐 `/workspace/main/patent-draft.md`、`/workspace/main/claims.md` 和 `/workspace/reports/claim-risk-review.md`。未知类型使用 `generic` profile。Lead-owned sandbox runtime 在 acquire 后会用 Lead 已知的 workspace type 刷新 mounted `/workspace/.wenjin/manifest.json`，并把轻量 `workspace_layout` / `workspace_profile` 写入 DataService environment metadata；复用已有 active environment 时会合并新的 runtime metadata，避免 provider 初始 generic manifest、管理面和 subagent context profile 分裂。新增业务类型应优先扩展 profile，不新增平行目录或 provider 分支。初始化会在 `/workspace/main/README.md` 写入简短目录使用规范，在 `/workspace/datasets/README.md` 写入数据集使用规范，并在 `/workspace/datasets/manifest.json(schema=wenjin.workspace_sandbox.dataset_provenance.v1)` 创建可编辑 dataset provenance 清单，在 `/workspace/reports/artifacts.json(schema=wenjin.workspace_sandbox.artifact_manifest.v1)` 创建可编辑 artifact metadata 清单；已有主项目 README、dataset manifest 或 artifact manifest 不会被覆盖。`datasets/scripts/outputs/reports` 会放置 `.gitkeep`。Lead runtime 加载 workspace source context 时统一使用 DataService source page 内嵌的 `assets`，把已经显式位于 `/workspace/datasets/**` 的 source asset 转成 `workspace_file_summary.dataset_provenance`；普通 Library 上传的 `references/...` 不会被伪装成 sandbox dataset。harness context bundle 会携带 bounded `workspace_file_summary`：visible roots、dataset provenance、recent scripts、recent outputs/reports 都从 `build_agent_workspace_contract().path_classes` 派生并过滤 protected/internal refs；bundle 也会携带 `workspace_profile`、`task_scratch_root=/workspace/tmp/tasks` 与 `search_ignored_names`，让 agent 同时理解垂直默认命名约定、任务临时文件位置和 list/search 默认跳过的常见缓存与依赖目录。预算过小时会先裁剪 recent execution evidence、file summary、sandbox rules 和 search ignore 列表这类可恢复上下文，避免突破 `max_chars` 并尽量保留用户 task。Lead-owned `sandbox.run_python` 会在脚本执行前、同一个 workspace lease 内把这份安全 dataset provenance 合并到 `/workspace/datasets/manifest.json`，只追加 sandbox contract datasets path class 下的数据文件并保留用户已有条目优先权，不把 manifest/README/.gitkeep、protected/internal refs、非 workspace refs 或普通 outputs 写入 manifest。tool-using ReactSubagent 也可以在 capability 与 skill 都允许时调用 `sandbox.register_dataset` 维护同一份 manifest；该工具只接受 `/workspace/datasets/**` 数据文件，复用 layout merge/sanitization，拒绝 guidance/protected/internal/non-dataset path，过滤 host path 与 secret ref 值，写入前要求 `filesystem.write` 和 `filesystem.diff`，并把 manifest diff 作为普通 harness `file_change` 记录。`sandbox.register_artifact` 用同样权限边界维护 `/workspace/reports/artifacts.json`，只接受 `/workspace/outputs/**` 或 `/workspace/reports/**` 的用户可审阅文件，拒绝 `/workspace/tmp/tasks/.harness/outputs/**`、manifest/guidance、protected/internal、host path 和 non-artifact refs，并把 title、description、artifact_kind、source_script、dataset_paths、notes 等安全字段用于后续 artifact discovery enrich。harness 新链路只使用 `/workspace`，不再新增 `/mnt/user-data` alias。layout 模块同时提供 normalize/classify/protected/internal/reviewable artifact 判断，文件工具、artifact discovery 和 sandbox review staging 共用这套分类；`HarnessPolicy` 默认 `protected_paths` 也来自这套 layout 常量，所以直接构造 policy 的测试、mock 或未来工具入口不会比 resolver 生产路径更宽。model-facing file tools 的入参必须已经是 `/workspace` 虚拟路径；provider stdout/stderr、listing 和 artifact discovery 可以把物理 sandbox root 反解回 `/workspace`，但不能把宿主绝对路径当作合法工具入参。`sandbox.list_dir`、`sandbox.glob` 和 `sandbox.grep` 会过滤 protected/internal 路径，避免 `.env`、`.wenjin/**` 或 `/workspace/tmp/tasks/.harness/outputs/**` 被 agent 当作普通文件发现；list/search 还会跳过 `node_modules`、`__pycache__`、`.venv`、`venv`、`site-packages`、`.pytest_cache`、`.mypy_cache`、`.ruff_cache`、`.next`、`.turbo` 等常见 generated/cache 目录，降低模型被依赖包、构建缓存和临时索引噪声干扰的概率；list/search 还会按 resolved physical target 跳过指向 workspace 外部、protected target 或 internal target 的 symlink，避免泄露外部文件、受保护文件、内部 refs 或 host physical path；direct `sandbox.read_file` 会拒绝 protected 路径和非 output-ref internal 路径，明确的 internal output ref 优先通过 `sandbox.read_output_ref` bounded 只读回看；`sandbox.write_file`、`sandbox.str_replace` 和 `sandbox.apply_patch` 会拒绝 protected/internal 路径，并在 provider 调用前校验目标 resolved physical path 仍在 `/workspace`，且反推回 workspace virtual path 后不是 protected/internal target，把 symlink escape 统一归一成 harness path policy error；Local provider listing 对 workspace 内部 symlink 保留链接自身的 virtual path，避免 `name=linked.txt,path=target.txt` 这种不一致投影；`read_file(max_chars=...)`、`glob(max_matches=...)` 和 `grep(max_matches=...)` 的调用参数只能进一步收窄 policy 上限，不能放大 `read_max_chars` 或 `search_max_matches`；externalized preview 的 head/tail 正文片段同样不能通过 `preview_head_chars` / `preview_tail_chars` 超过 fallback budget；`list_dir` 的 preview 和 structured `entries` 共用 `search_max_matches` 上限，并返回 total/returned 计数；`glob` / `grep` 的 structured `matches` 也同样 bounded，并返回 `returned_matches` / `match_limit`；`grep(literal=true)` 会把 pattern 当普通文本搜索，默认仍是 regex；`grep` 按 `grep_max_file_bytes` / `grep_max_line_chars` 跳过超大文件、二进制文件和超长行，并返回扫描/跳过计数；非法 regex 只返回 recoverable JSON tool error，不扫描文件、不中断 agent loop。工具大输出的当前外部化目录为 `/workspace/tmp/tasks/.harness/outputs/{execution_id}/{node_id}/{invocation_id}/`；模型只接收 bounded preview 和 refs，完整 stdout/read_file 内容与大 unified diff 留在 workspace sandbox 内；明确的 output ref 可通过 `sandbox.read_output_ref(output_ref,start_line,end_line,max_chars)` bounded 只读回看，但不能被 list/search 发现，不能写入、替换或注册为用户 artifact。`sandbox.apply_patch` 是结构化多文件 patch 工具，只支持 `replace` 和 `write` edit，会先校验全部 edit、唯一匹配和路径边界，再执行任何 mutation；它返回 `file_changes[]` 供多文件 diff evidence 聚合。Lead-owned `sandbox.run_python` 还会在 lease 内扫描 `/workspace/outputs` 与 `/workspace/reports`，把非 internal 的用户可审阅文件作为 `generated_artifacts[]` 候选项返回；扫描会跳过 `.gitkeep` 和 `/workspace/reports/artifacts.json`，并用 artifact manifest 中同 path 的安全元数据丰富候选项。普通 LangGraph runtime 与 TeamKernel 都会把可信候选注册为 `workspace_asset(storage_backend=sandbox)` 和 `sandbox_artifact` review item，用户接受后才进入 materialized 状态。

TeamKernel 通过 `backend/src/agents/lead_agent/v2/team/member_context.py` 为每个实名成员生成 bounded input：优先保留用户显式 `query/topic/goal/raw_message`，缺 query 时从 raw message 的英文术语或紧凑原文派生检索 query，并附加 role-specific `task_focus`、team blackboard 和 upstream summary；protected/internal `/workspace/.wenjin/**`、`/workspace/tmp/tasks/.harness/outputs/**` refs 会在进入成员上下文前过滤。这样 `research_scout` 不再依赖 graph-template inputs 才能拿到检索 query。

ReactSubagent 只要带 sandbox 工具或 capability sandbox policy，就会通过 `backend/src/agents/harness/context_assembly.py` 构造同一份 `_harness_context(schema=wenjin.harness.context_bundle.v1)` bounded bundle，并同时注入默认 payload 与 system prompt 的 `Harness context bundle` 段落。bundle 是 harness-enabled 团队成员的执行上下文 schema：top-level 暴露 `capability_goal`、`member_role`、`allowed_tools`、`workspace_roots`、`search_ignored_names`、最新 `recent_file_change_summary`、`sandbox_execution_summary`、`reproducibility_summary`、`harness_replan_signals` 和 `upstream_artifact_candidates`；同时保留任务摘要、workspace 类型、`/workspace` sandbox contract、artifact roots、protected/internal paths、recent execution evidence 和预算信息。recent execution evidence 和上游产物候选都会过滤 protected/internal workspace refs，并携带 node-level reproducibility 的脚本路径、产物路径、依赖名和 job/environment id 摘要，让后续团队成员能接续已有实验而不读取 raw tool JSON 或内部 refs。预算过小时，context assembly 会先裁剪 recent execution evidence、上游产物、replan signals、最新 harness summaries 和 workspace file summary，最后才丢弃 task。
工具型 ReactSubagent 会在 LangGraph ReAct loop 的 `pre_model_hook` 里执行本地消息完整性修复：若 provider/model 历史里出现 structured、raw provider 或 invalid tool call 但缺少对应 `ToolMessage`，运行时会补一个 bounded synthetic error tool result，并使用 LangGraph 的 `RemoveMessage(REMOVE_ALL_MESSAGES)` 覆盖旧消息序列。这个修复只保护 provider 消息顺序和下一轮模型调用，不创建新的事件流、不执行额外工具、不把 raw invalid args、host path 或 protected workspace path 写入 synthetic message；正常无缺失时 hook 只返回 `llm_input_messages`，不改变 durable execution state。

Agent harness 第一版把 ReactSubagent 的工具请求接到同一条执行链：`library_read/document_read/memory_read/prism_read/citation_parser/artifact_create` 这些 business-context tools 读取 bounded workspace snapshot 或返回 staged artifact payload，不直接提交 rooms、写 Prism 或物化 artifact；调用记录会写入 `_harness_tool_records` 并随节点记录进入 `ExecutionNodeRecord.tool_calls`。`sandbox.list_dir/glob/grep/read_file/read_output_ref/write_file/str_replace/apply_patch/register_dataset/register_artifact/run_python` 由 capability/skill policy 过滤，sandbox 工具通过 workspace scheduler 串行，tool calls 写回对应 `ExecutionNodeRecord.tool_calls`，debug 事件走现有 `execution.harness.*` stream；business-context tools 和 sandbox tools 共用 `backend/src/agents/harness/args_summary.py` 作为 debug args 摘要边界，`citation_parser.text`、`artifact_create.markdown`、`sandbox.run_python.script`、`sandbox.write_file.content`、`sandbox.apply_patch.edits` 和 `dependency_hints` 这类可能携带大文本或未校验输入的工具参数只记录 `chars` / `items` / `sha256` 摘要，不把原文写入 debug args；如果工具入参在 LangChain/Pydantic schema 层校验失败，adapter 会返回 `error_code=tool_input_validation` 的 recoverable JSON tool result，并把字段级 validation summary 写入 failed tool record，且不会回显 raw invalid payload。文件工具只允许访问 `/workspace`，受保护路径来自 workspace layout：`.git/**`、根目录和子目录 `.env` / `.env.*`、`*.pem`、`*.key`、`.wenjin/**`；读/list/search 工具在实现边界也要求 `filesystem.read`，写工具、`sandbox.apply_patch`、`sandbox.register_dataset` 和 `sandbox.register_artifact` 在 mutation 前同时要求 `filesystem.write` / `filesystem.diff`，不能只依赖上层 registry 过滤；list/search 会过滤这些 protected 路径和 `/workspace/tmp/tasks/.harness/outputs/**` internal refs，直接 read/write/str_replace/apply_patch 也会拒绝 protected/internal 路径，以及 resolved target 落到 workspace 外、protected 或 internal 的 symlink。本地 sandbox provider 会在 command stdout/stderr 边界把物理 workspace 路径反解回 `/workspace`，保证本地测试、mock sandbox 和 Docker sandbox 的 public 文件系统契约一致，避免宿主机路径进入 harness 结果或 agent 上下文。`list_dir`、`glob`、`grep`、`read_file` 和 Lead-owned `sandbox.run_python` stdout/stderr 已接入 output budget / result bounding：超过阈值或数量上限时只返回 bounded payload，并把必要 refs、`externalized`、`truncated` 标记返回给 tool result、tool call record 和 `execution.harness.output_externalized` 事件。`sandbox.write_file` / `sandbox.str_replace` / `sandbox.apply_patch` / `sandbox.register_dataset` / `sandbox.register_artifact` 的 hash + unified diff 会进入 tool call record、`execution.harness.tool_call.completed` 和 `execution.harness.file_change` 事件；小 diff 直接保留，大 diff 以 `unified_diff` 预览 + `diff_output_refs` 引用形式外部化到 `/workspace/tmp/tasks/.harness/outputs/**`；Lead runtime 与 TeamKernel 会把同一批 tool call 聚合为 `node_metadata.harness.file_change_summary`，供节点详情和后续审阅面读取。单次 harness tool exception 会在 adapter 边界降级为 bounded JSON error result，同时写入 `status=failed` tool record 和 `execution.harness.tool_call.failed` 事件，模型可以带着错误上下文继续执行；TeamKernel 还会把 failed / recoverable tool calls 聚合为 `node_metadata.harness.tool_failure_summary(schema=wenjin.harness.tool_failure_summary.v1)`，后续 replanning、运行详情和质量门不需要解析 raw tool JSON；`sandbox.run_python` 的 `execution_manifest`、`reproducibility_manifest`、`experiment_narrative` 与 `failure_classification` 会投影到 tool record metadata / completed event metadata，并进一步聚合为 `node_metadata.harness.sandbox_execution_summary(schema=wenjin.harness.sandbox_execution_summary.v1)` 和 `node_metadata.harness.reproducibility_summary(schema=wenjin.harness.reproducibility_summary.v1)`：前者记录 Python run 数、失败数、recoverable failure 数、sandbox job/environment ids、failure codes 与 generated artifact count，后者记录 manifest/narrative 数、脚本路径、dataset/artifact 路径、依赖名、sandbox job/environment ids、install job ids、command risk levels 和 next actions；`node_metadata.harness.run_journal_summary(schema=wenjin.harness.run_journal_summary.v1)` 是 RunView 优先读取的成员进度摘要，事件 envelope 也会携带 `journal(schema=wenjin.harness.journal_event.v1)` 作为现有 execution event path 上的精简进度条目。`python_exit_nonzero` / `sandbox_queue_timeout` / `tool_forbidden` / `tool_unknown` 会生成 `node_metadata.harness.replan_signals(schema=wenjin.harness.replan_signal.v1)`，TeamKernel 只把 latest signals 写入 blackboard 并交给 `harness_replan_signal` quality gate：非零退出可做一次同模板修订，queue timeout 和 forbidden/unknown tool 不会触发重复招募。只有 LangGraph 控制流信号和 loop guard hard stop 会继续硬停止。重复相同工具调用达到 warning 阈值时，harness 发布 `execution.harness.loop_warning(team_visible)`，但不会往模型消息序列中插入 warning。command audit 基座已落在 `backend/src/agents/harness/command_audit.py`：Lead-owned `run_python`、`install_dependencies` 和 smoke check sandbox jobs 写入 `metadata.command_audit`，其中 `policy_decision(schema=wenjin.harness.command_policy_decision.v1)` 明确记录 `allow/forbid`、reason 和 bounded command preview；forbid 会在创建 sandbox job 与 acquire sandbox 前被硬拦截，网络/提权程序、host path、protected/internal workspace path 和非规范 pip spec 不进入运行态。harness `sandbox.run_python` 会把 run/install 审计带回 payload、tool record、completed event，并发布 `execution.harness.command_audit(team_visible)`；不向 subagent 暴露通用 `sandbox.run_command`。默认 UI 仍展示团队成员进度和交付物，不直接展示 raw tool JSON。

当前 `policy_decision` 字段全集是 `operation`、`decision`、`risk_level`、`reason`、`network_profile`、`billable`、`blocked_before_job` 和 `command_preview`。`install_dependencies` 使用 `package_index_only` 网络 profile 且 `billable=false`；`run_python` 与 `smoke_check` 是 billable sandbox jobs；所有 `forbid` decision 都表示 job 创建前阻断。

`tool_input_validation` 现在也会生成 `node_metadata.harness.replan_signals(schema=wenjin.harness.replan_signal.v1)`，recommended action 为 `revise_tool_call_args`。TeamKernel 的 `harness_replan_signal` quality gate 会把它作为同模板修订处理，让原成员按工具 schema 修正参数再试一次；它不触发权限升级或额外补位成员。
`tool_input_validation` 还会发布 `execution.harness.tool_call.failed(debug_only)`，payload 只包含 tool name、validation summary、recoverable error metadata 和 result preview，保证 live run stream 与 node metadata 都能看到这类失败，但不会暴露 raw invalid args。

TeamKernel quality gates 当前会写入 `ExecutionRecord.runtime_state.quality_gates`，用于刷新或历史恢复后的 LiveWorkflowPanel/RunView 展示；这不是新的执行事实源，只是从 TeamKernel blackboard 导出的运行态摘要。节点运行详情仍由 `ExecutionNodeRecord` 拥有；Gateway/API read path 会通过 `ExecutionService` 把 `execution_nodes` hydrate 回 `ExecutionRecord.node_states`，保证 list/detail/Current run 能恢复团队成员、工具摘要和 harness metadata。前端默认进展只展示 `准备上下文 -> 组建团队 -> 成员执行 -> 质量闭环 -> 整理结果` 五步流程；实名成员列表和成员 harness activity 归 team roster 展示，成员模板不会再作为 `team_template_*` 流程占位节点出现。质量门展示会按 gate id 聚合为当前状态，避免历史 quality gate event 重复刷屏。证据闭环里，QualityContract 会携带当前 workspace 的 `allowed_citation_keys` 和 `allowed_source_ids`；`claim_evidence_map_required` 会校验每条 supported claim 是否同时包含 claim 文本和当前 workspace 允许的 `source_id` 或 `citation_key`；仅有 claim/evidence 描述、无来源锚点或引用了 workspace 外 citation key 的输出会要求成员修订。`source-quality-auditor` / `citation-auditor` 的结构化输出也进入质量门：source authority、metadata completeness、weak support、fabricated citation、claim-source binding 和 style consistency 这些 gate 不能只靠 prose/acknowledgement 通过，必须返回 `citation_key_audit`、`missing_sources`、`fabrication_risks` 或 `bibtex_projection_notes` 等字段；字段里的 citation/source refs 若出现，必须属于当前 workspace allowlist；若 audit row 标记 `fabricated`、`not_ready`、`replace`、`missing`、`unsupported`、`weak` 或 high/critical/blocking severity，会要求成员修订而不是被当作通过。

## 5. Result Card 闭环流程

1. Chat Agent 调用 `launch_feature` → chat stream 输出 `tool_invocation` / `tool_result`
2. `tool_result.status == "advisory"` → ChatPanel 渲染补充上下文提示，闭环停在 chat，不进入 execution / billing / external search
3. `tool_result.status == "launched"` → ChatPanel 渲染启动回执，`run-ui-store` 标记 active run
4. capability 执行完成 → `TaskReport` 含 `outputs[]`
5. SSE `execution.completed` 事件 → 前端 execution-store
6. `useWorkspaceEventStream` 统一拥有 execution 发现和 execution stream 订阅，从 ExecutionRecord 提取 TaskReport → 构造 ResultCardData → chat store
7. ResultCard 在聊天面板渲染：按 kind 分组、checkbox 选取；Prism 写作变更渲染为 DB-backed review item
8. Prism review item 可从 ResultCard / CompletedView / chat block 进入 `/workspaces/{workspace_id}/prism?focus=file_changes&review_item_id=...&logical_key=...`
9. 用户 commit → `POST /api/executions/{id}/commit` → `ExecutionCommitService` 按 kind 路由到对应 room service
10. Prism 写作变更必须先走 Prism apply/reject/revert；接受后才写入稿件文件
11. commit / apply 后通过 canonical `workspace.refresh` 事件刷新 room drawers、workspace activity 和 Prism context

## 5.1 Execution UX 当前收敛

1. `frontend/lib/execution-run-view.ts` 是前端执行展示投影事实源，负责从 `ExecutionRecord`、Runs `RunRecord`、chat `result_card` 派生统一 `RunView`
2. `frontend/stores/run-ui-store.ts` 只保存 UI 焦点：active / focused / highlighted / completed run ids；不拥有执行状态事实
3. LiveWorkflowPanel 会 pin 当前 run：running 时自动展开执行卡，completed 后保持 Current run 摘要；active/focused 的非终态 run 优先于历史抽屉里的 stale selection，避免新启动团队任务被旧记录遮住
4. Runs toolbar 按钮显示运行中/已完成提示；Runs drawer 合并 live execution store 与 `/api/workspaces/{workspace_id}/runs` 历史记录
5. `/api/workspaces/{workspace_id}/runs` projection 已补齐 `workspace_id`、`thread_id`、`capability_id`、`progress`、`primary_surface`、`review_items_count`、`has_prism_changes`、`failure_category`、`failure_message`
6. Prism tab / result card / Runs drawer 在存在 review items 时显示 pending handoff；Prism review state 仍以 canonical `review_items` 为准
7. 浏览器 smoke 已验证：workspace query seed 启动 `sci_literature_positioning` → chat launch receipt → right panel Current run running → completed → Runs drawer 历史记录，无需手动刷新
8. 浏览器 smoke 已验证：runtime-staged Prism writing review item → `/workspaces/{workspace_id}/prism` pending diff → `应用到 Prism` → `review_summary.pending_count=0/applied_count=1`
9. 浏览器 smoke 已验证：TeamKernel execution read path hydrate 后，LiveWorkflowPanel 能从 `execution_nodes` 恢复全部团队实名成员，并从 `runtime_state.quality_gates` 恢复质量检查数量；默认展示不暴露 raw tool JSON。
10. 浏览器 smoke 已验证：历史 TeamKernel run 在刷新后展示为五步任务进展，顶部计数与步骤列表一致；旧 `team_template_*` 不再显示为“工作步骤/待处理”，质量门从历史事件列表聚合为当前 gate 状态。

## 6. Prism 主稿协作面

1. Prism 是 workspace 的第二主 surface，canonical route 为 `/workspaces/{workspace_id}/prism`
2. `LatexProject.workspace_id + surface_role=primary_manuscript` 是 workspace 与主稿项目的绑定事实
3. LaTeX editor/compile/file-change endpoints 只作为 Prism adapter 暴露在 `/api/prism/latex-adapter/*`；旧 `/api/latex/*` 不提供兼容层、fallback 或 redirect
4. Canonical `review_items` 是文件变更 review 状态事实源；ResultCard、CompletedView、Compute、Prism Changes 共享同一 projection
5. Canonical `provenance_links` 记录稿件变更与 Library / Documents / execution 输出的 provenance
6. Canonical `prism_protected_scopes` 记录用户手动保护的稿件范围，并进入后续 agent launch context
7. `WorkspacePrismService` 对外提供 surface projection：main file、target files、pending/applied review items、source links、protected sections、activity、compile status
8. `TaskBrief.manuscript_context` 只注入 lightweight manuscript projection，不传完整正文、完整 diff 或 PDF
9. `research_question_to_paper`、`idea_to_thesis_manuscript` 和 TeamKernel 写作成员的 `manuscript_writer` 输出已声明为 `prism_file_change`，runtime 完成后写入 canonical review item。
10. DataService review batch/action log 是 Prism review 的事务边界；batch/items 先 flush，action log 后写入，保证独立 DataService + Postgres 部署下 FK 顺序稳定。
11. Prism adapter routers 和 LaTeX/WorkspacePrism runtime services 通过 DataService client 访问 Latex/Prism/Review/Source facts，不再携带 runtime DB session。
12. Long-term memory runtime、memory compaction、Celery memory capture 与 workspace-context upload memory note 通过 Knowledge DataService client 访问 persistence，不再携带 runtime DB session 或执行 request-time commit/rollback。
13. DashboardService / WorkspaceSummaryService 和 gateway dashboard dependencies 通过 DataService-backed construction 访问 dashboard、summary 和 execution facts，不再携带 runtime DB session。
14. Workspace capability action resolve 和 WorkspaceContextMiddleware 通过 Workspace/Catalog/Template DataService-backed services 访问 workspace/action/template facts，不再注入 `get_db` 或自行打开 `get_db_session`。
15. Admin capability / skill catalog 的 router、service、validator 和 seed loader 通过 Catalog DataService client 访问 persistence，不再携带 runtime DB session；seed/admin/runtime 共用 `capability.v2` / `capability_skill.v2` schema。
16. Reference Library、BibTeX export/validation 和 Prism `refs.bib` sync 通过 Source/Asset/Prism DataService client 访问 persistence，不再在 references router 或 `SourceBibliographyService` 中注入 DB session；运行时 enum / request contract 来自 `dataservice_client.contracts.source`，DB reference model 只属于持久化层。
17. Source domain 的 Library reference projection 是当前契约；list/detail helper 不再以 `compat` 命名承载当前 API shape。
18. Catalog skill projection 只读取完整 canonical `skill_json`；空缺或空对象直接失败，不再从旧列读时合成 skill pack。
19. Thread、Template、WorkspaceActivity、AdminAnalytics 和 workspace skill label helper 均已收敛为 DataService-backed facade，不再保留可选 DB 构造参数。
20. Gateway common deps 已移除通用 `get_db`；ExecutionService、TaskStore、SkillResolver、CapabilityResolver、WorkspaceService、GenerationService 均不再接受历史 DB/session 构造参数，workspace 运行链路只通过 DataService client 触达持久化。
21. Documents room 和 workspace activity 的 asset projection 只读取 canonical metadata 字段，不再在运行时读取 `legacy_kind`、`legacy_parent_id`、`legacy_version`。
22. Gateway routers 的 `current_user` / admin subject 均以 `AccountAuthSubject` 标注，不再导入 DB `User` model 作为运行时鉴权类型。
23. Prism adapter metadata 在 DataService helper 和 runtime projection 中均只暴露 `source_metadata`，不再把 project metadata 放进 `legacy_metadata` 字段。
24. Worker execution 解析 workspace type 时只读取 DataService workspace projection；workspace 或 type 缺失会显式失败，不再默认降级为 thesis。
25. Feature execution params 只保留 canonical TaskBrief wrapper；旧 plain-param execution params 解析入口已移除。
26. Artifact follow-up / rerun action state 只从显式 mission params 或来源 artifact 推导 goal；缺少上下文时返回不可重跑原因，前后端均不再用 workspace 描述、`fallbackTaskName` 或“未命名任务”兜底。
27. Workspace upload stored path 只接受 workspace-relative path 或 workspace-root 内绝对路径；历史 cwd-relative 全根路径不再由运行时解析。
28. Conversation block payload 只持久化 canonical `kind`，不再写入旧 kind 的 shadow 字段。
29. React subagent 请求 tools 但没有解析到 callable 时显式失败；不会把工具型节点静默当作普通 LLM 节点执行。
30. `AuditService` 只通过 Audit DataService client 写入和查询审计记录，不再暴露 `session_factory` / ORM model 构造入口。
31. Execution commit 接受 Library outputs 后会通过同一个 Source/Prism DataService client 同步 Prism `refs.bib`，不依赖 execution service 上的 DB session。
32. Gateway / Worker 进程生命周期不再初始化、重置或关闭 DB engine；Gateway readiness 检查 DataService `/readyz`，worker bootstrap 只处理 Sentry、Redis 和 MCP runtime。
33. Thread / workspace runtime helper 的类型注解使用 DataService payload contract，不再引用 DB `Thread` / `Workspace` model。

## 7. 前端信息架构

1. **Workspace shell**：提供 Workbench / Prism 两个主 surface switch
2. **Workbench 左面板**（Chat）：对话与结果卡片入口
3. **Workbench 右面板**（Execution / Compute）：Current run、execution graph、node 详情、room drawers、Compute Stage
4. **Prism surface**：LaTeX editor、compile/PDF、Changes review、workspace context rail
5. Room drawers（顶部 toolbar）：Library / Documents / Tasks / Runs 等；Runs drawer 是执行历史与审计面，不是第二套运行状态源
6. Settings page：Memory / Decisions / Settings 管理；Sandbox 不在 Settings 或顶栏 room 中暴露为用户操作台

### 7.1 全站 UIUX 收敛原则

1. Workbench、Prism、rooms、admin、settings 统一遵守“自动适配 + 信息分层”原则。
2. 页面应根据 viewport、当前 run、完成态和选中项自动调整展示面；不得要求用户理解或手动恢复内部 focus/lock 状态。
3. 窄区域默认 list-first；点击条目后进入详情面或 fullscreen split view。宽屏才并列展示列表与详情。
4. 二级导航、筛选和次级操作应轻量化：icon-only + tooltip、compact segmented controls、pills 优先，避免重复文字按钮和大卡片堆叠。
5. 列表中的长标题、作者、文件名、URL 和 run 名必须截断；完整内容只在详情区展示。

## 8. 线程模型

1. single-thread-per-workspace 的主体验模型
2. thread 仍是服务端持久化单元，用于恢复和历史
3. assistant thread message 的 `metadata.orchestration.execution_id` 会持久化，用于 result card 归属与刷新后恢复

## 9. 文档优先级

1. 当前行为以本文件、`workspace-feature-catalog.md`、`docs/current/architecture.md` 为准。
2. 历史方案和阶段性过渡文档已清理；追溯请查看 Git 历史。
3. WenjinPrism 划词改写采用 `preview -> apply -> revert`：
   - `preview` 只生成候选和 diff，不写文件。
   - `apply` 在后端执行签名/哈希校验、结构门禁和编译门禁，通过后写文件。
   - `revert` 使用 `apply` 返回的撤销 payload 做一次性回滚。
4. 结构性风险由后端强约束兜底；前端 risk/diff 主要用于语义判断与人工审阅，不承担安全职责。
5. 写作类 feature 对已有 Prism 文件不直接覆盖，生成内容进入 `file_changes`：
   - `file-changes/preview` 生成 diff 和签名。
   - `file-changes/apply` 必须携带 preview 签名。
   - `file-changes/discard` 丢弃待确认写入。
   - `file-changes/revert` 使用 `applied_file_changes` 中的签名和文件 hash 撤回。
6. Workbench ResultCard、CompletedView、chat result block 和 Prism Changes 共享 `WorkspacePrismReviewItem` / `PrismReviewList`。
7. Prism apply / reject / revert / protect 会写入 canonical review state、protected scope 或 workspace activity，不走 frontend-only 状态。
8. 当前 UX 约定：
   - 支持候选切换、inline/side-by-side、hunk 折叠、空白改动过滤、重生成、复制候选。
   - 支持快捷键：`Ctrl/Cmd + Enter` 应用候选，`Esc` 取消预览。
