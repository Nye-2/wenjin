# Runtime Boundary Convergence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the remaining auth/account, artifact/asset, and LaTeX public-route historical boundaries and converge them on AccountDataService, AssetDataService, and Prism manuscript adapter architecture.

**Architecture:** The migration is split into three independently verifiable domains. Auth removes request-time DB session dependency and returns an Account DataService subject. Artifact removes `legacy_artifact` runtime naming while preserving DataService ownership. LaTeX routes move from public `/latex/*` to Prism adapter routes with no compatibility layer.

**Tech Stack:** Python 3.13, FastAPI, Pydantic v2, SQLAlchemy async inside DataService/database ownership only, pytest; Next.js 16, React 19, TypeScript, Vitest.

---

## Implementation Status

更新时间：2026-05-30

已完成并提交：

- `86f10cef refactor: route auth through account dataservice`
  - `get_current_user` / `get_current_admin` 返回 Account DataService subject。
  - auth token helper 与 `UserService` 不再携带 runtime DB session。
- `c57e5efd refactor: canonicalize workspace artifact boundary`
  - Runtime contract 收敛到 `WorkspaceArtifact*` / Asset DataService。
  - `legacy_artifact` 命名退出 runtime surface。
- `4f93cba3 refactor: route latex surface through prism adapter`
  - 前端/后端 manuscript adapter API 收敛到 `/api/prism/latex-adapter/*`。
  - `/api/latex/*` 不提供 compatibility layer、fallback 或 redirect。
  - Prism adapter routers、LaTeX services、WorkspacePrism/WorkspaceLatex services 通过 DataService client 访问 persistence，不再接受 runtime DB session。
- `6ec02fc8 refactor: close gateway dataservice runtime boundaries`
  - thread/run launch owner check、execution commit 和 compute projection 不再依赖 request DB session。
  - Gateway runtime 通过 DataService client 执行 workspace owner、commit、compute shell/projection 读写。
- Current execution runtime boundary follow-up
  - `/executions/*` runtime API、`launch_feature`、task recovery/cancel 和 worker execution lifecycle 不再以 DB session 构造 `ExecutionService`。
  - `launch_feature` 直接从 Workspace/Catalog DataService 解析 workspace type 和 capability，并通过 Execution DataService 创建/恢复/标记 dispatch metadata。
  - Worker `execute_execution` 运行时不再打开 DB session、不再 reset DB engine、不再通过 `ThreadService(db)` 写回 result_card。
  - `LeadAgentRuntime` 不再接收或保存 DB session；Prism BibTeX 同步通过 Reference/DataService service 自己的 canonical client 边界执行。
  - `CapabilityResolver` 运行时解析只依赖 Catalog DataService client，不接受 session factory 或 DB constructor。
  - Generic `execute_task` 预处理 worker 不再打开 DB session、不再 reset DB engine；任务记录、线程结果卡片、附件 preprocess 状态统一通过 Task/Conversation DataService client 写回。
  - Gateway `get_task_service` 不再为 TaskService 创建 request-time DB session，TaskStore 只需要 Redis runtime cache 与 DataService client。
  - Thread run worker、ProgressTracker stage transition flush、Task SSE initial snapshot 不再打开 DB session；统一通过 Run/Task/Conversation DataService client 访问运行态持久化。
  - Gateway `get_thread_service` / `get_workspace_service` 不再依赖 request DB session；ThreadTurnHandler 清理遗留 `get_db_session` import，线程/工作区运行时依赖改为 DataService-only service construction。
- Current memory runtime boundary follow-up
  - `user_memory_service`、`memory_compaction` 和 Celery `capture_memory` 不再打开 DB session 或 reset DB engine。
  - 长期记忆读取、提取写入、压缩归档统一通过 `KnowledgeService(dataservice=...)` 和 Knowledge DataService client 执行。
  - `KnowledgeService` 构造器移除 DB/session 参数，不再保存 `db/self.db/_db`。
  - Workspace context 上传写入长期记忆时复用请求注入的 DataService client，不再为 memory note 注入 DB、commit 或 rollback。
  - Architecture guard 新增 `test_memory_runtime_uses_dataservice_knowledge_boundary`，防止 memory runtime、uploads memory note 和 KnowledgeService facade 回流到 session-based persistence。
- Current dashboard runtime boundary follow-up
  - Gateway dashboard dependencies 不再注入 `get_db` 或 `AsyncSession`；DashboardService、WorkspaceActivityService、WorkspaceSummaryService 均以 DataService-backed construction 进入 runtime。
  - `DashboardService` 构造器移除 DB/session 参数。
  - `WorkspaceSummaryService` 构造器移除 DB/session 参数，默认通过 `ExecutionService(dataservice=...)` 获取 execution history，不再以 DB fallback 构造 execution service。
  - Architecture guard 新增 `test_dashboard_runtime_uses_dataservice_boundary`，防止 dashboard deps 和 summary/dashboard facade 回流到 request DB session。
- Current workspace runtime boundary follow-up
  - `resolve_workspace_capability_action` 移除未使用的 request DB dependency，capability/action/artifact facts 均通过 Workspace/Catalog/Asset DataService client 解析。
  - `WorkspaceContextMiddleware` 加载 active template 时改用 DataService-backed `TemplateService`，不再自行打开 DB session。
  - Middleware 支持注入 `template_service`，测试和 runtime 均通过同一 DataService-backed service contract。
  - Architecture guard 新增 `test_workspace_runtime_uses_dataservice_boundary`，防止 workspace route/action context 回流到 `get_db` 或 `get_db_session`。
- Current admin catalog runtime boundary follow-up
  - `admin_capabilities` / `admin_skills` 管理端 router 不再打开 `get_db_session`；service construction 和 seed import 均通过请求注入的 Catalog DataService client。
  - `AdminCapabilityService`、`AdminSkillService`、`CrossRefValidator`、`CapabilityLoader`、`SkillLoader` 移除 DB/session 构造参数，Catalog CRUD、cross-ref 校验和 seed load 统一走 DataService client。
  - `bootstrap_admin` 只负责创建管理员账号的 DB-owned bootstrap；skills/capabilities seed load 调用 DataService-backed loader，不把 bootstrap session 传入 catalog runtime。
  - Architecture guard 新增 `test_admin_catalog_runtime_uses_dataservice_boundary`，防止 admin catalog router/service/loader/validator 回流到 request DB session。
- Current reference library runtime boundary follow-up
  - `references` gateway router 不再导入 `AsyncSession` 或 `get_db`，Prism `refs.bib` sync 复用请求注入的 Source/Prism DataService client。
  - `SourceBibliographyService` 移除 DB/session 构造参数，不再保存 `self.db`；BibTeX export、citation validation、Prism refs sync 均通过 DataService client 完成。
  - Architecture guard 新增 `test_reference_library_runtime_uses_dataservice_boundary`，防止 references router 和 bibliography service 回流到 request DB session。
- Current service facade boundary follow-up
  - `ThreadService`、`TemplateService`、`WorkspaceActivityService`、`AdminAnalyticsService` 移除 DB/session 构造参数，不再保存 `self.db`。
  - `workspace_skill_labels` 移除 `db` 参数，workspace type lookup 通过传入的 DataService client 或 canonical DataService provider 完成。
  - Gateway/thread worker service construction 不再传 `ThreadService(None, ...)`；测试 fixtures 同步为 DataService-only construction。
  - Architecture guard 新增 `test_runtime_service_facades_do_not_keep_optional_db_sessions`，防止 runtime facade 重新引入可选 DB constructor。
- Current legacy helper boundary follow-up
  - Gateway common deps 移除通用 `get_db` dependency export，只保留 DataService client 和 domain service factories。
  - `ExecutionService`、`TaskStore`、`SkillResolver` 移除历史 DB/session 构造参数和 `self.db`/`_db` 保存点。
  - Upload、execution cancel/display、engine、task store/service、skill resolver 单测同步到 DataService-only construction。
  - Architecture guard 新增 `test_legacy_gateway_and_execution_helpers_do_not_keep_db_sessions`，防止已退役 helper/facade 重新暴露 DB session。
- Current catalog/academic facade boundary follow-up
  - `CapabilityResolver` 移除 `session_factory` 参数；capabilities router 使用 Account auth subject，不再导入 DB `User`。
  - `WorkspaceService`、`GenerationService` 移除 DB/session 构造参数和 `self.db` 保存点。
  - Gateway academic dependency 与 thread run worker 不再传 `WorkspaceService(None, ...)`。
  - Architecture guard 新增 `test_catalog_and_academic_facades_do_not_keep_db_constructors`，防止 Catalog/academic facade 回流到 DB constructor。
- Current workspace asset metadata boundary follow-up
  - Documents room asset projection 移除 `legacy_kind`、`legacy_parent_id`、`legacy_version` 读取，只使用 canonical `kind`、`parent_id`、`version` 和 DataService asset fields。
  - Workspace activity artifact projection 移除 `legacy_kind` 读取，只使用 canonical `artifact_type` / `asset_kind`。
  - Architecture guard 新增 `test_workspace_asset_runtime_projections_do_not_read_legacy_metadata_fields`，防止 router/activity projection 重新读取 legacy metadata。
- Current gateway auth subject boundary follow-up
  - Gateway routers 不再导入 DB `User` model 作为 `current_user` / admin subject 类型。
  - 所有 router auth 注解统一为 `AccountAuthSubject`，`get_current_user_optional` 对应 `AccountAuthSubject | None`。
  - MCP router 从 canonical `auth_dependencies` 导入 `get_current_user`，不再从 auth router 反向取依赖。
  - Architecture guard 新增 `test_gateway_routers_do_not_type_auth_subjects_as_database_users`，防止 router 层重新引入 DB `User` auth subject。
- Current Prism adapter metadata boundary follow-up
  - `WorkspacePrismService` adapter metadata 对外字段收敛为 canonical `source_metadata`。
  - `legacy_metadata` 不再出现在 runtime Prism adapter surface projection 中。
  - `_list_prism_review_items` 类型注解收敛到 DataService client contract `ReviewItemPayload`，不引用 DataService 内部 projection 类型。
  - Architecture guard 新增 `test_prism_adapter_metadata_uses_canonical_field_names`，防止 Prism adapter metadata 重新暴露 legacy field。
- Current DataService Prism adapter metadata follow-up
  - `dataservice.domains.prism.adapters.latex.build_latex_adapter_metadata` 输出字段同步收敛为 `source_metadata`。
  - Architecture guard 扩展到 DataService adapter helper，防止 `legacy_metadata` 在更深层重新出现。
- Current execution workspace type boundary follow-up
  - `execute_execution` 的 Lead runtime workspace type resolver 改为 `_resolve_execution_workspace_type`。
  - Workspace type 只从 DataService workspace projection 读取，支持 `workspace_type` / `type` projection shape。
  - workspace 不存在或 type 为空时显式抛错并由 execution engine 标记 failed，不再默认使用 thesis。
  - Architecture guard 扩展 `test_execution_runtime_uses_dataservice_execution_boundary`，防止恢复 fallback resolver 或 `or "thesis"`。
- Current feature launch params boundary follow-up
  - `extract_feature_params` 旧 plain-param parser 已删除。
  - Feature execution launch params 只通过 `build_execution_launch_params` 生成 canonical TaskBrief wrapper。
  - Architecture guard 新增 `test_feature_launch_context_does_not_keep_plain_param_compatibility`，防止恢复旧执行参数兼容入口。
- Current feature action goal boundary follow-up
  - `FeatureActionResolutionService` 不再从 workspace description/name 或“未命名任务”合成 rerun goal。
  - Rerun/follow-up state 只从显式 mission params 或 source artifact title/content 推导。
  - `_GOAL_KEYS` 补齐 `description`、`keywords`，确保已有显式参数仍可生成 canonical goal。
  - Architecture guard 新增 `test_feature_action_resolution_does_not_synthesize_workspace_goal_fallbacks`。
- Current frontend feature action boundary follow-up
  - `workspace-feature-actions.ts` 删除 `fallbackTaskName` / `workspaceFallback`。
  - `FeatureActionResolverContext` 不再包含 fallback task name 字段。
  - Frontend follow-up / rerun state 只消费 backend SSOT 返回的 route/rerun params。
- Current workspace upload path boundary follow-up
  - `resolve_workspace_upload_stored_path` 删除 cwd-relative workspace-root-prefixed 历史路径解析分支。
  - Stored path 只接受 workspace-relative path、root-prefixed virtual relative path（显式 `allow_root_prefixed_relative=True`）或 workspace-root 内绝对路径。
  - Architecture guard 新增 `test_workspace_uploads_do_not_accept_legacy_root_prefixed_relative_paths`。
- Current React requested-tools boundary follow-up
  - React subagent 请求 tools 且 `_resolve_tools` 未返回 callable 时显式抛错。
  - 删除“tools 解析为空就退回 plain model invoke”的 TODO/注释口径。
  - Architecture guard 新增 `test_react_subagent_does_not_silently_ignore_requested_tools`。
- Current Catalog skill canonical JSON boundary follow-up
  - `skill_to_record` 要求 Catalog DB row 携带完整 canonical `skill_json`。
  - 空缺或空对象直接抛错，不再从旧字段读时合成 skill pack。
  - Architecture guard 新增 `test_catalog_skill_projection_does_not_synthesize_legacy_skill_json`。
- Current Source reference projection naming follow-up
  - `SourceDataDomainService` 的 Library list/detail helper 重命名为 `_serialize_reference_projection`。
  - API 返回的 `reference` shape 仍是当前 Library 契约，不再以 `compat` 命名描述。
  - Architecture guard 新增 `test_source_domain_does_not_name_current_reference_projection_as_compat`。
- Current conversation block payload boundary follow-up
  - `normalize_block_payload` 只写入 canonical `kind`，不再保留旧 kind/type 的 shadow 字段。
  - Conversation block protocol 继续保持 7 类 canonical block 持久化契约。
  - Architecture guard 新增 `test_conversation_block_payloads_do_not_persist_legacy_kind`。
- Current execution generation usage naming follow-up
  - `GenerationRecordCreateCommand` / `GenerationRecordProjection` 文案收敛为当前 DataService-owned usage contract。
  - 不再把 generation usage projection 描述为 legacy record。
  - Architecture guard 新增 `test_execution_generation_contracts_do_not_label_current_usage_projection_legacy`。
- Current DataService stale naming cleanup
  - `rooms.models` 文案改为 database-model archive gate。
  - Source BibTeX citation key 默认值参数改为 `default_key`。
  - DataService / DataService app / DataService client 源码的 stale keyword scan 已无 `legacy|compat|fallback|TODO|backward|deprecated` 命中。
  - Architecture guard 新增 `test_dataservice_internal_contracts_do_not_keep_legacy_or_fallback_naming`。
- Current workspace capability runtime comment follow-up
  - Chat Agent text summary docstring 不再描述 old consumers；改为 transport text summary。
  - Deep-link selected skill 注释收敛为 DB-backed capability catalog routing。
  - Frontend workspace thread seed 注释收敛为 server-side capability/skill routing。
  - Architecture guard 新增 `test_workspace_capability_runtime_comments_do_not_keep_legacy_guidance`。
- Current production source legacy label cleanup
  - Execution model docstring、feature flag tombstone、literature context、thread event 注释收敛为当前语义。
  - Migration bootstrap constant 从 `LEGACY_BOOTSTRAP_STAMP_REVISION` 改为 `CREATE_ALL_BOOTSTRAP_STAMP_REVISION`。
  - Production source `legacy` scan 已无命中；测试和迁移断言仍可保留历史词用于证明退役路径。
  - Architecture guard 新增 `test_production_source_does_not_keep_unscoped_legacy_labels`。
- Current audit/reference contract boundary follow-up
  - `AuditService` 移除 `session_factory` / ORM model 构造参数，只通过 Audit DataService client 写入和查询审计记录。
  - Reference Library router 和 `SourceBibliographyService` 的运行时 enum/request contract 收敛到 `dataservice_client.contracts.source`。
  - `SourceBibliographyService` 移除对 `src.database.base.generate_uuid` 的依赖，内部临时 ID 生成使用标准库 `uuid4`。
  - Architecture guard 新增 `test_audit_service_stays_on_audit_dataservice_boundary` 和 `test_reference_library_runtime_uses_dataservice_contract_boundary`，防止审计与 Reference Library 运行时回流到 DB-shaped contract。

已验证：

- `cd backend && .venv/bin/python -m pytest tests/architecture/test_dataservice_boundaries.py::test_audit_service_stays_on_audit_dataservice_boundary tests/architecture/test_dataservice_boundaries.py::test_reference_library_runtime_uses_dataservice_contract_boundary -q` -> red first: 2 failed; after implementation: 2 passed.
- `cd backend && .venv/bin/python -m ruff check src/services/audit_service.py src/gateway/routers/references.py src/services/references/service.py src/dataservice_client/contracts/source.py tests/database/test_audit_logs.py tests/integration/test_phase1_foundation.py tests/architecture/test_dataservice_boundaries.py` -> passed.
- `cd backend && .venv/bin/python -m pytest tests/architecture/test_dataservice_boundaries.py::test_audit_service_stays_on_audit_dataservice_boundary tests/architecture/test_dataservice_boundaries.py::test_reference_library_runtime_uses_dataservice_contract_boundary tests/database/test_audit_logs.py tests/integration/test_phase1_foundation.py::test_audit_log_and_query tests/services/test_reference_usage_service.py tests/services/test_reference_writing_workflow_gate.py tests/services/test_reference_bibtex_service.py tests/services/test_reference_index_service.py tests/services/test_reference_import_service.py tests/tools/test_reference_builtins.py -q` -> 32 passed.
- `cd backend && .venv/bin/python -m pytest tests/architecture/test_dataservice_boundaries.py -q` -> 38 passed.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/ -q` -> 2036 passed.
- `cd backend && .venv/bin/python -m ruff check src/config/feature_flags.py src/agents/middlewares/literature_context.py src/database/migration_bootstrap.py src/database/models/execution.py src/services/thread_events.py tests/database/test_migration_bootstrap.py tests/architecture/test_dataservice_boundaries.py` -> passed.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/architecture/test_dataservice_boundaries.py::test_production_source_does_not_keep_unscoped_legacy_labels tests/database/test_migration_bootstrap.py -q` -> 7 passed.
- `rg -ni "legacy" backend/src frontend/app frontend/components frontend/hooks frontend/lib frontend/stores -g '*.{py,ts,tsx}'` -> no matches.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/architecture/test_dataservice_boundaries.py -q` -> 36 passed.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/ -q` -> 2034 passed.
- `cd backend && .venv/bin/python -m ruff check src/agents/chat_agent/agent.py tests/architecture/test_dataservice_boundaries.py` -> passed.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/architecture/test_dataservice_boundaries.py::test_workspace_capability_runtime_comments_do_not_keep_legacy_guidance -q` -> 1 passed.
- `cd frontend && npm run typecheck` -> passed.
- `rg -n "legacy consumers|legacy per-skill guidance prompt|legacy resolver" backend/src/agents/chat_agent/agent.py frontend/lib/workspace-thread-entry.ts` -> no matches.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/architecture/test_dataservice_boundaries.py -q` -> 35 passed.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/ -q` -> 2033 passed.
- `cd backend && .venv/bin/python -m ruff check src/dataservice/domains/source/service.py src/dataservice/domains/rooms/models.py tests/architecture/test_dataservice_boundaries.py` -> passed.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/dataservice/test_source_provenance_domain.py tests/dataservice/test_rooms_domain.py tests/architecture/test_dataservice_boundaries.py::test_dataservice_internal_contracts_do_not_keep_legacy_or_fallback_naming -q` -> 21 passed.
- `rg -n "legacy|compat|fallback|TODO|backward|deprecated" backend/src/dataservice backend/src/dataservice_app backend/src/dataservice_client -g '*.py'` -> no matches.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/architecture/test_dataservice_boundaries.py -q` -> 34 passed.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/ -q` -> 2032 passed.
- `cd backend && .venv/bin/python -m ruff check src/dataservice/domains/execution/contracts.py tests/architecture/test_dataservice_boundaries.py` -> passed.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/architecture/test_dataservice_boundaries.py::test_execution_generation_contracts_do_not_label_current_usage_projection_legacy -q` -> 1 passed.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/architecture/test_dataservice_boundaries.py -q` -> 33 passed.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/ -q` -> 2031 passed.
- `cd backend && .venv/bin/python -m ruff check src/dataservice/domains/conversation/block_protocol.py tests/dataservice/test_conversation_domain.py tests/architecture/test_dataservice_boundaries.py` -> passed.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/dataservice/test_conversation_domain.py tests/architecture/test_dataservice_boundaries.py::test_conversation_block_payloads_do_not_persist_legacy_kind -q` -> 5 passed.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/architecture/test_dataservice_boundaries.py -q` -> 32 passed.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/ -q` -> 2030 passed.
- `cd backend && .venv/bin/python -m ruff check src/dataservice/domains/source/service.py tests/architecture/test_dataservice_boundaries.py` -> passed.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/dataservice/test_source_provenance_domain.py tests/architecture/test_dataservice_boundaries.py::test_source_domain_does_not_name_current_reference_projection_as_compat -q` -> 17 passed.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/architecture/test_dataservice_boundaries.py -q` -> 31 passed.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/ -q` -> 2029 passed.
- `cd backend && .venv/bin/python -m ruff check src/dataservice/domains/catalog/projection.py tests/dataservice/test_catalog_domain.py tests/architecture/test_dataservice_boundaries.py` -> passed.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/dataservice/test_catalog_domain.py tests/dataservice/test_foundation.py tests/services/test_capability_resolver.py tests/services/test_admin_skill_service.py tests/architecture/test_dataservice_boundaries.py::test_catalog_skill_projection_does_not_synthesize_legacy_skill_json -q` -> 43 passed.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/architecture/test_dataservice_boundaries.py -q` -> 30 passed.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/ -q` -> 2028 passed.
- `cd backend && .venv/bin/python -m ruff check src/subagents/v2/types/react.py tests/unit/subagents/test_react.py tests/architecture/test_dataservice_boundaries.py` -> passed.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/unit/subagents/test_react.py tests/agents/lead_agent/v2/test_runtime.py tests/agents/lead_agent/v2/test_failure_handling.py tests/agents/lead_agent/v2/test_compiler.py tests/architecture/test_dataservice_boundaries.py::test_react_subagent_does_not_silently_ignore_requested_tools -q` -> 43 passed.
- `cd backend && .venv/bin/python -m pytest tests/architecture/test_dataservice_boundaries.py -q` -> 29 passed.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/ -q` -> 2025 passed.
- `cd backend && .venv/bin/python -m ruff check src/services/workspace_uploads.py tests/services/test_workspace_uploads.py tests/architecture/test_dataservice_boundaries.py` -> passed.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/services/test_workspace_uploads.py tests/services/test_template_service.py tests/services/test_reference_import_service.py tests/agents/middlewares/test_uploads_middleware.py tests/task/test_document_preprocess_handler.py tests/gateway/routers/test_uploads.py tests/architecture/test_dataservice_boundaries.py::test_workspace_uploads_do_not_accept_legacy_root_prefixed_relative_paths -q` -> 28 passed.
- `cd backend && .venv/bin/python -m pytest tests/architecture/test_dataservice_boundaries.py -q` -> 28 passed.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/ -q` -> 2023 passed.
- `cd backend && .venv/bin/python -m ruff check src/services/feature_action_resolution_service.py tests/task/test_workspace_feature_actions_runtime.py tests/architecture/test_dataservice_boundaries.py` -> passed.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/task/test_workspace_feature_actions_runtime.py tests/gateway/routers/test_workspace_activity.py tests/architecture/test_dataservice_boundaries.py::test_feature_action_resolution_does_not_synthesize_workspace_goal_fallbacks -q` -> 36 passed.
- `cd backend && .venv/bin/python -m pytest tests/architecture/test_dataservice_boundaries.py -q` -> 27 passed.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/ -q` -> 2021 passed.
- `cd frontend && npm run test -- tests/unit/lib/workspace-feature-actions.test.ts tests/unit/lib/workspace-feature-action-context.test.ts` -> 4 passed.
- `cd frontend && npm run typecheck` -> passed.
- `cd backend && .venv/bin/python -m ruff check src/application/services/feature_launch_context.py tests/application/services/test_feature_launch_context.py tests/architecture/test_dataservice_boundaries.py` -> passed.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/application/services/test_feature_launch_context.py tests/tools/test_launch_feature_tool.py tests/integration/test_chat_to_feature_launch.py tests/architecture/test_dataservice_boundaries.py::test_feature_launch_context_does_not_keep_plain_param_compatibility -q` -> 18 passed.
- `cd backend && .venv/bin/python -m pytest tests/architecture/test_dataservice_boundaries.py -q` -> 26 passed.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/ -q` -> 2020 passed.
- `cd backend && .venv/bin/python -m ruff check src/task/tasks/execution.py tests/task/test_execution_result_card_persistence.py tests/architecture/test_dataservice_boundaries.py` -> passed.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/task/test_execution_result_card_persistence.py tests/task/test_thread_writeback.py tests/services/test_execution_cancel.py tests/execution/test_engine.py tests/agents/lead_agent/v2/test_runtime.py tests/agents/lead_agent/v2/test_failure_handling.py tests/architecture/test_dataservice_boundaries.py::test_execution_runtime_uses_dataservice_execution_boundary -q` -> 49 passed.
- `cd backend && .venv/bin/python -m pytest tests/architecture/test_dataservice_boundaries.py -q` -> 25 passed.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/ -q` -> 2019 passed.
- `cd backend && .venv/bin/python -m ruff check src/services/workspace_prism_service.py tests/services/test_workspace_prism_service.py tests/architecture/test_dataservice_boundaries.py` -> passed.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/services/test_workspace_prism_service.py tests/gateway/routers/test_workspace_prism.py tests/execution/test_engine.py tests/architecture/test_dataservice_boundaries.py::test_prism_adapter_metadata_uses_canonical_field_names -q` -> 23 passed.
- `cd backend && .venv/bin/python -m pytest tests/architecture/test_dataservice_boundaries.py -q` -> 25 passed.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/ -q` -> 2017 passed.
- `cd backend && .venv/bin/python -m ruff check src/dataservice/domains/prism/adapters/latex.py src/services/workspace_prism_service.py tests/dataservice/test_prism_latex_adapter_metadata.py tests/architecture/test_dataservice_boundaries.py` -> passed.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/dataservice/test_prism_latex_adapter_metadata.py tests/services/test_workspace_prism_service.py tests/gateway/routers/test_workspace_prism.py tests/architecture/test_dataservice_boundaries.py::test_prism_adapter_metadata_uses_canonical_field_names -q` -> 15 passed.
- `cd backend && .venv/bin/python -m pytest tests/architecture/test_dataservice_boundaries.py -q` -> 29 passed.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/ -q` -> 2026 passed.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/ -q` -> 2007 passed.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/task/test_execution_result_card_persistence.py tests/task/test_thread_writeback.py tests/services/test_capability_resolver.py tests/gateway/routers/test_capabilities_router.py tests/gateway/test_capabilities_router.py tests/agents/lead_agent/v2/test_runtime.py tests/agents/lead_agent/v2/test_cancel_flow.py tests/agents/lead_agent/v2/test_failure_handling.py tests/architecture/test_dataservice_boundaries.py -q` -> 59 passed.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/task tests/gateway/routers/test_uploads.py tests/architecture/test_dataservice_boundaries.py -q` -> 141 passed.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/ -q` -> 2007 passed.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/task/test_progress.py tests/task/test_sse.py tests/task/test_task_metrics.py tests/task/test_agent_status.py tests/gateway/test_run_lifecycle_dispatch.py tests/gateway/routers/test_thread_runs.py tests/architecture/test_dataservice_boundaries.py -q` -> 54 passed.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/task tests/gateway/test_run_lifecycle_dispatch.py tests/gateway/routers/test_thread_runs.py tests/architecture/test_dataservice_boundaries.py -q` -> 150 passed.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/ -q` -> 2007 passed.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/gateway/routers/test_threads.py tests/gateway/routers/test_threads_router.py tests/gateway/routers/test_thread_runs.py tests/gateway/routers/test_uploads.py tests/gateway/routers/test_artifacts.py tests/gateway/test_run_lifecycle_dispatch.py tests/task tests/architecture/test_dataservice_boundaries.py -q` -> 223 passed.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/ -q` -> 2007 passed.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/services/test_memory_compaction.py tests/services/test_memory_capture_service.py tests/agents/memory/test_capture.py tests/agents/memory/test_llm_updates.py tests/agents/middleware/test_memory.py tests/gateway/routers/test_memory.py tests/services/test_knowledge_service.py tests/gateway/routers/test_uploads.py tests/architecture/test_dataservice_boundaries.py::test_memory_runtime_uses_dataservice_knowledge_boundary -q` -> 52 passed.
- `cd backend && .venv/bin/python -m ruff check src/services/user_memory_service.py src/services/memory_compaction.py src/services/knowledge_service.py src/task/tasks/memory.py src/gateway/routers/uploads.py tests/services/test_memory_compaction.py tests/agents/memory/test_llm_updates.py tests/agents/middleware/test_memory.py tests/gateway/routers/test_uploads.py tests/services/test_knowledge_service.py tests/architecture/test_dataservice_boundaries.py` -> passed.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/architecture/test_dataservice_boundaries.py -q` -> 15 passed.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/ -q` -> 2008 passed.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/services/test_dashboard_service.py tests/services/test_workspace_summary_service.py tests/gateway/routers/test_dashboard.py tests/gateway/routers/test_dashboard_center.py tests/architecture/test_dataservice_boundaries.py -q` -> 43 passed.
- `cd backend && .venv/bin/python -m ruff check src/gateway/deps/dashboard.py src/services/dashboard_service.py src/services/workspace_summary_service.py tests/services/test_dashboard_service.py tests/services/test_workspace_summary_service.py tests/architecture/test_dataservice_boundaries.py` -> passed.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/ -q` -> 2009 passed.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/agents/middlewares/test_workspace_context.py tests/agents/middlewares/test_middlewares.py tests/agents/middlewares/test_academic_middlewares.py tests/agents/middlewares/test_context_timeouts.py tests/gateway/routers/test_dashboard.py tests/gateway/routers/test_workspace_prism.py tests/architecture/test_dataservice_boundaries.py -q` -> 46 passed.
- `cd backend && .venv/bin/python -m ruff check src/gateway/routers/workspaces.py src/agents/middlewares/workspace_context.py tests/agents/middlewares/test_workspace_context.py tests/agents/middlewares/test_middlewares.py tests/agents/middlewares/test_academic_middlewares.py tests/gateway/routers/test_workspace_prism.py tests/architecture/test_dataservice_boundaries.py` -> passed.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/ -q` -> 2011 passed.
- `cd backend && .venv/bin/python -m pytest tests/services/test_admin_capability_service.py tests/services/test_admin_capability_service_crud.py tests/services/test_admin_skill_service.py tests/services/test_cross_ref_validator.py tests/services/test_capability_loader.py tests/seed/test_capability_seeds_load.py tests/unit/services/test_skill_loader.py tests/integration/test_phase1_foundation.py::test_capability_load_resolve_invalidate tests/integration/test_phase2_e2e.py::test_lead_agent_runtime_with_seeded_capability_completes tests/architecture/test_dataservice_boundaries.py::test_admin_catalog_runtime_uses_dataservice_boundary -q` -> 42 passed.
- `cd backend && .venv/bin/python -m ruff check src/gateway/routers/admin_capabilities.py src/gateway/routers/admin_skills.py src/services/admin_capability_service.py src/services/admin_skill_service.py src/services/capability_schema.py src/services/capability_loader.py src/services/skill_loader.py src/database/bootstrap_admin.py tests/services/test_admin_capability_service.py tests/services/test_admin_capability_service_crud.py tests/services/test_admin_skill_service.py tests/services/test_cross_ref_validator.py tests/services/test_capability_loader.py tests/seed/test_capability_seeds_load.py tests/unit/services/test_skill_loader.py tests/integration/test_phase1_foundation.py tests/integration/test_phase2_e2e.py tests/architecture/test_dataservice_boundaries.py` -> passed.
- `cd backend && .venv/bin/python -m pytest tests/architecture/test_dataservice_boundaries.py -q` -> 18 passed.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/ -q` -> 2012 passed.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/services/test_reference_writing_workflow_gate.py tests/services/test_reference_bibtex_service.py tests/services/test_reference_import_service.py tests/gateway/routers/test_access_control_matrix.py tests/architecture/test_dataservice_boundaries.py::test_reference_library_runtime_uses_dataservice_boundary -q` -> 29 passed.
- `cd backend && .venv/bin/python -m ruff check src/gateway/routers/references.py src/services/references/service.py tests/services/test_reference_writing_workflow_gate.py tests/architecture/test_dataservice_boundaries.py` -> passed.
- `cd backend && .venv/bin/python -m pytest tests/architecture/test_dataservice_boundaries.py -q` -> 19 passed.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/ -q` -> 2013 passed.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/services/test_thread_service.py tests/services/test_template_service.py tests/services/test_workspace_activity_service.py tests/services/test_admin_analytics_service.py tests/gateway/routers/test_threads.py tests/gateway/routers/test_threads_router.py tests/gateway/routers/test_thread_runs.py tests/gateway/routers/test_dashboard.py tests/gateway/routers/test_dashboard_center.py tests/architecture/test_dataservice_boundaries.py::test_runtime_service_facades_do_not_keep_optional_db_sessions -q` -> 101 passed.
- `cd backend && .venv/bin/python -m ruff check src/services/thread_service.py src/services/template_service.py src/services/workspace_activity_service.py src/services/admin_analytics_service.py src/services/workspace_skill_labels.py src/gateway/deps/threads.py src/task/tasks/run.py tests/services/test_thread_service.py tests/services/test_workspace_activity_service.py tests/architecture/test_dataservice_boundaries.py` -> passed.
- `cd backend && .venv/bin/python -m pytest tests/architecture/test_dataservice_boundaries.py -q` -> 20 passed.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/ -q` -> 2014 passed.
- `cd backend && .venv/bin/python -m ruff check src/gateway/deps/core.py src/gateway/deps/__init__.py src/services/execution_service.py src/task/store.py src/services/skill_resolver.py tests/gateway/routers/test_uploads.py tests/services/test_execution_cancel.py tests/test_execution_display_name.py tests/execution/test_engine.py tests/task/conftest.py tests/task/test_store.py tests/task/test_service.py tests/unit/services/test_skill_resolver.py tests/architecture/test_dataservice_boundaries.py` -> passed.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/services/test_execution_cancel.py tests/test_execution_display_name.py tests/execution/test_engine.py tests/task/test_store.py tests/task/test_service.py tests/task/test_task_metrics.py tests/unit/services/test_skill_resolver.py tests/gateway/routers/test_uploads.py tests/architecture/test_dataservice_boundaries.py::test_legacy_gateway_and_execution_helpers_do_not_keep_db_sessions -q` -> 66 passed.
- `cd backend && .venv/bin/python -m pytest tests/architecture/test_dataservice_boundaries.py -q` -> 21 passed.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/ -q` -> 2014 passed.
- `cd backend && .venv/bin/python -m ruff check src/services/capability_resolver.py src/gateway/routers/capabilities.py src/academic/services/workspace_service.py src/gateway/deps/academic.py src/task/tasks/run.py src/academic/services/generation_service.py tests/services/test_capability_resolver.py tests/integration/test_phase1_foundation.py tests/integration/test_phase2_e2e.py tests/academic/services/test_workspace_service.py tests/academic/services/test_generation_service.py tests/architecture/test_dataservice_boundaries.py` -> passed.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/services/test_capability_resolver.py tests/gateway/test_capabilities_router.py tests/gateway/routers/test_capabilities_router.py tests/integration/test_phase1_foundation.py::test_capability_load_resolve_invalidate tests/integration/test_phase2_e2e.py::test_lead_agent_runtime_with_seeded_capability_completes tests/academic/services/test_workspace_service.py tests/academic/services/test_generation_service.py tests/gateway/routers/test_threads.py tests/task/test_thread_writeback.py tests/architecture/test_dataservice_boundaries.py::test_catalog_and_academic_facades_do_not_keep_db_constructors -q` -> 45 passed.
- `cd backend && .venv/bin/python -m pytest tests/architecture/test_dataservice_boundaries.py -q` -> 22 passed.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/ -q` -> 2014 passed.
- `cd backend && .venv/bin/python -m ruff check src/gateway/routers/workspace_rooms.py src/services/workspace_activity_service.py tests/gateway/routers/test_workspace_room_document_assets.py tests/architecture/test_dataservice_boundaries.py` -> passed.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/gateway/routers/test_workspace_room_document_assets.py tests/gateway/routers/test_workspace_rooms_router.py tests/services/test_workspace_activity_service.py tests/architecture/test_dataservice_boundaries.py::test_workspace_asset_runtime_projections_do_not_read_legacy_metadata_fields -q` -> 41 passed.
- `cd backend && .venv/bin/python -m pytest tests/architecture/test_dataservice_boundaries.py -q` -> 23 passed.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/ -q` -> 2015 passed.
- `cd backend && .venv/bin/python -m ruff check src/gateway/routers tests/architecture/test_dataservice_boundaries.py` -> passed.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/gateway/routers tests/architecture/test_dataservice_boundaries.py::test_gateway_routers_do_not_type_auth_subjects_as_database_users -q` -> 210 passed.
- `cd backend && .venv/bin/python -m pytest tests/architecture/test_dataservice_boundaries.py -q` -> 24 passed.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/ -q` -> 2016 passed.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/gateway/routers/test_latex_upload_limits.py tests/gateway/routers/test_latex_workspace_route_convergence.py tests/services/test_latex_hardening.py tests/services/test_workspace_prism_service.py tests/services/test_prism_review_workflow_gate.py tests/services/test_reference_writing_workflow_gate.py tests/gateway/routers/test_workspace_prism.py tests/compute/test_projection_service.py tests/architecture/test_dataservice_boundaries.py -q` -> 88 passed.
- `cd frontend && npm run test -- tests/unit/lib/prism-review-api.test.ts` -> 5 passed.
- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/ -q` -> 2005 passed.
- `cd frontend && npm run typecheck` -> passed.
- `cd frontend && npm run build` -> passed.
- `git diff --check` -> passed.

当前发布前统一门禁已通过。

---

## File Structure

### Auth / Account

- Modify `backend/src/gateway/auth_dependencies.py`
  - remove `Depends(get_db)` and `AsyncSession`
  - return Account auth subject projection
- Modify `backend/src/services/auth.py`
  - remove `db` parameters from token persistence helpers
- Modify `backend/src/services/user_service.py`
  - remove `db` constructor and stale docstring
- Modify routers currently typing `current_user: User`
  - import and use the auth subject type where practical
  - keep field access unchanged
- Modify tests:
  - `backend/tests/gateway/routers/test_auth.py`
  - `backend/tests/services/test_auth.py`
  - `backend/tests/services/test_auth_email_workflow_gate.py`
  - architecture guard tests

### Artifact / Asset

- Modify `backend/src/dataservice/domains/asset/contracts.py`
  - rename legacy artifact contracts to canonical workspace artifact names
- Modify `backend/src/dataservice/domains/asset/projection.py`
- Modify `backend/src/dataservice/domains/asset/service.py`
- Modify `backend/src/dataservice/asset_api.py`
- Modify `backend/src/dataservice_app/routers/asset.py`
- Modify `backend/src/dataservice_client/contracts/asset.py`
- Modify `backend/src/dataservice_client/client.py`
- Modify `backend/src/academic/services/artifact_service.py`
  - remove `db`
  - remove compatibility wording
  - call canonical client methods
- Modify runtime call sites under gateway/application/task services.
- Modify artifact tests and architecture guards.

### Prism LaTeX Adapter

- Create or modify router prefix under `backend/src/gateway/routers/prism_latex_adapter*.py`
- Remove old `/latex/*` router registration from gateway app configuration
- Modify LaTeX services:
  - `backend/src/services/latex/project_service.py`
  - `backend/src/services/latex/template_service.py`
  - `backend/src/services/latex/compile_service.py`
  - `backend/src/services/workspace_latex_projects.py`
  - `backend/src/services/workspace_prism_service.py`
- Modify frontend clients:
  - `frontend/lib/api/latex.ts` or replacement `frontend/lib/api/prism-latex-adapter.ts`
  - every importer of the LaTeX API client
- Modify backend route tests and frontend API tests.
- Extend architecture guards against `/latex` runtime routes and frontend calls.

---

## Task 1: Auth Subject And Token Helper Boundary

**Files:**
- Modify: `backend/src/gateway/auth_dependencies.py`
- Modify: `backend/src/services/auth.py`
- Modify: `backend/src/services/user_service.py`
- Modify: `backend/tests/architecture/test_dataservice_boundaries.py`
- Test: `backend/tests/gateway/routers/test_auth.py`
- Test: `backend/tests/services/test_auth.py`
- Test: `backend/tests/services/test_auth_email_workflow_gate.py`

- [ ] **Step 1: Add failing architecture guard for auth DB dependency**

Add a test in `backend/tests/architecture/test_dataservice_boundaries.py`:

```python
def test_auth_runtime_stays_on_account_dataservice_boundary() -> None:
    checked_files = [
        SRC_ROOT / "gateway" / "auth_dependencies.py",
        SRC_ROOT / "services" / "auth.py",
        SRC_ROOT / "services" / "user_service.py",
    ]
    forbidden_imports = {"sqlalchemy.ext.asyncio"}
    forbidden_names_by_module = {
        "src.database": {"User", "get_db_session"},
        "src.gateway.deps.core": {"get_db"},
    }

    violations: list[str] = []
    for path in checked_files:
        relative = path.relative_to(SRC_ROOT)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        visitor = _RuntimeImportVisitor()
        visitor.visit(tree)
        for node in visitor.import_from_nodes:
            module = node.module or ""
            if module in forbidden_imports:
                violations.append(f"{relative}:{node.lineno} imports {module}")
            forbidden_names = forbidden_names_by_module.get(module, set())
            imported_forbidden_names = sorted(
                alias.name for alias in node.names if alias.name in forbidden_names
            )
            if imported_forbidden_names:
                violations.append(
                    f"{relative}:{node.lineno} imports {module}.{', '.join(imported_forbidden_names)}"
                )

    assert not violations, "Auth runtime must use Account DataService only:\n" + "\n".join(violations)
```

- [ ] **Step 2: Run guard and verify failure**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/architecture/test_dataservice_boundaries.py::test_auth_runtime_stays_on_account_dataservice_boundary -q
```

Expected: FAIL listing `AsyncSession`, `User`, and/or `get_db` imports.

- [ ] **Step 3: Implement AccountAuthSubject**

Add to `backend/src/gateway/auth_dependencies.py`:

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class AccountAuthSubject:
    id: str
    email: str
    name: str | None
    role: str
    is_active: bool
    is_superuser: bool
    credits: int = 0
    created_at: datetime | None = None
    last_login: datetime | None = None
    refresh_token_hash: str | None = None
    refresh_token_expires_at: datetime | None = None

    @classmethod
    def from_record(cls, user: Any) -> "AccountAuthSubject":
        return cls(
            id=str(user.id),
            email=str(user.email),
            name=getattr(user, "name", None),
            role=str(getattr(user, "role", "admin" if getattr(user, "is_superuser", False) else "user")),
            is_active=bool(getattr(user, "is_active", False)),
            is_superuser=bool(getattr(user, "is_superuser", False)),
            credits=int(getattr(user, "credits", 0) or 0),
            created_at=getattr(user, "created_at", None),
            last_login=getattr(user, "last_login", None),
            refresh_token_hash=getattr(user, "refresh_token_hash", None),
            refresh_token_expires_at=getattr(user, "refresh_token_expires_at", None),
        )
```

- [ ] **Step 4: Remove auth dependency DB session**

Change `get_current_user` and `get_current_user_optional` so they accept only credentials and `dataservice`. Return `AccountAuthSubject.from_record(user)`.

- [ ] **Step 5: Remove `db` from token helpers**

In `backend/src/services/auth.py`:

- `_get_user_record(user_id, *, dataservice=None)`
- `persist_refresh_token(*, user, refresh_token, dataservice=None)`
- `revoke_refresh_token(*, user, dataservice=None)`
- `create_and_persist_tokens(*, user_id, email, role="user", user=None, dataservice=None)`
- `verify_refresh_token_recorded(token, *, dataservice=None)`

Update all call sites in `backend/src/gateway/routers/auth.py`.

- [ ] **Step 6: Remove `db` from UserService**

In `backend/src/services/user_service.py`, remove `AsyncSession`, `db`, and stale docstring language.

- [ ] **Step 7: Run auth tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/gateway/routers/test_auth.py tests/services/test_auth.py tests/services/test_auth_email_workflow_gate.py tests/architecture/test_dataservice_boundaries.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/src/gateway/auth_dependencies.py backend/src/services/auth.py backend/src/services/user_service.py backend/src/gateway/routers/auth.py backend/tests
git commit -m "refactor: route auth subject through account dataservice"
```

## Task 2: Canonical Workspace Artifact Contracts

**Files:**
- Modify: `backend/src/dataservice/domains/asset/contracts.py`
- Modify: `backend/src/dataservice/domains/asset/projection.py`
- Modify: `backend/src/dataservice/domains/asset/service.py`
- Modify: `backend/src/dataservice/asset_api.py`
- Modify: `backend/src/dataservice_app/routers/asset.py`
- Modify: `backend/src/dataservice_client/contracts/asset.py`
- Modify: `backend/src/dataservice_client/client.py`
- Modify: `backend/src/academic/services/artifact_service.py`
- Modify: runtime call sites returned by `rg "legacy_artifact|legacy-artifacts|LegacyArtifact"`
- Test: artifact, dashboard, execution commit, and architecture tests

- [ ] **Step 1: Add failing guard for runtime legacy artifact names**

Add architecture guard that scans runtime packages outside `database`, `dataservice`, `dataservice_app`, and `dataservice_client` for `legacy_artifact`, `legacy-artifacts`, and `LegacyArtifact`.

- [ ] **Step 2: Run guard and verify failure**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/architecture/test_dataservice_boundaries.py::test_runtime_code_does_not_use_legacy_artifact_surface_names -q
```

Expected: FAIL with runtime files.

- [ ] **Step 3: Rename contracts**

Rename:

- `LegacyArtifactCreateCommand` -> `WorkspaceArtifactCreateCommand`
- `LegacyArtifactUpdateCommand` -> `WorkspaceArtifactUpdateCommand`
- `LegacyArtifactProjection` -> `WorkspaceArtifactProjection`

Keep field names compatible (`type`, `content`, `version`, `status`) unless tests require a broader product rename.

- [ ] **Step 4: Rename DataService routes**

Change internal route prefix from `/legacy-artifacts` to `/artifacts` in `backend/src/dataservice_app/routers/asset.py`.

- [ ] **Step 5: Rename DataService client methods**

Rename client methods to workspace artifact names and update all callers:

- `create_workspace_artifact`
- `get_workspace_artifact`
- `find_latest_workspace_artifact`
- `list_workspace_artifacts`
- `count_workspace_artifacts`
- `list_workspace_artifact_versions`
- `update_workspace_artifact`
- `delete_workspace_artifact`
- `get_workspace_artifact_lineage`

- [ ] **Step 6: Clean runtime ArtifactService**

Update `backend/src/academic/services/artifact_service.py`:

- remove `AsyncSession` and `db`
- remove compatibility wording
- call renamed client methods

- [ ] **Step 7: Update call sites and tests**

Use:

```bash
rg -n "legacy_artifact|legacy-artifacts|LegacyArtifact|count_legacy_artifacts|list_legacy_artifacts" backend/src backend/tests
```

Update every runtime/test caller to the canonical names.

- [ ] **Step 8: Run artifact/domain tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/dataservice tests/gateway/routers/test_artifacts.py tests/gateway/routers/test_workspace_rooms_router.py tests/services/test_dashboard_service.py tests/services/test_admin_dashboard_service.py tests/architecture/test_dataservice_boundaries.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add backend/src backend/tests
git commit -m "refactor: rename legacy artifacts to workspace artifacts"
```

## Task 3: Prism LaTeX Adapter Route Migration

**Files:**
- Modify/Create: `backend/src/gateway/routers/prism_latex_adapter.py`
- Modify/Delete old router registration for `latex_*` routers
- Modify: `backend/src/services/latex/project_service.py`
- Modify: `backend/src/services/latex/template_service.py`
- Modify: `backend/src/services/latex/compile_service.py`
- Modify: `backend/src/services/workspace_latex_projects.py`
- Modify: `backend/src/services/workspace_prism_service.py`
- Modify: `frontend/lib/api/latex.ts`
- Modify frontend importers of the LaTeX API client
- Test: backend LaTeX/Prism route tests and frontend API tests

- [ ] **Step 1: Add failing backend route guard**

Add guard:

```python
def test_runtime_does_not_register_public_latex_routes() -> None:
    router_root = SRC_ROOT / "gateway" / "routers"
    violations = []
    for path in router_root.glob("latex*.py"):
        violations.append(str(path.relative_to(SRC_ROOT)))
    assert not violations, "Public /latex route modules must be removed:\n" + "\n".join(violations)
```

Expected initial failure.

- [ ] **Step 2: Add failing frontend API guard**

Add or extend a frontend unit test to assert `frontend/lib/api/latex.ts` does not contain `"/latex`.

- [ ] **Step 3: Remove DB constructor dependencies from LaTeX services**

For each LaTeX/Prism adapter service constructor, remove:

```python
db: AsyncSession | None = None
self.db = db
```

Construct nested services with `dataservice=dataservice`.

- [ ] **Step 4: Create Prism adapter router**

Move the existing route functions from old `latex_*` router files under a new prefix:

```python
router = APIRouter(prefix="/prism/latex-adapter", tags=["prism", "latex-adapter"])
```

Replace every `LatexProjectService(db)` with `LatexProjectService(dataservice=dataservice)` and inject `dataservice: AsyncDataServiceClient = Depends(get_dataservice_client)`.

- [ ] **Step 5: Stop registering old LaTeX routers**

Remove old imports/includes from gateway app setup. Delete old `backend/src/gateway/routers/latex*.py` files after the new router covers all needed endpoints.

- [ ] **Step 6: Update frontend API prefix**

Change `frontend/lib/api/latex.ts` constants/calls from:

```ts
"/latex/projects"
`/latex/projects/${projectId}`
```

to:

```ts
"/prism/latex-adapter/projects"
`/prism/latex-adapter/projects/${projectId}`
```

If the file name remains `latex.ts`, add a top comment stating it is the Prism LaTeX adapter client, not a standalone LaTeX product API.

- [ ] **Step 7: Update backend tests**

Rename request URLs in route tests from `/latex/...` to `/prism/latex-adapter/...`. Add a test that `/latex/health` returns 404 through normal app routing.

- [ ] **Step 8: Run target tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/gateway/routers/test_latex* tests/services/test_latex* tests/services/test_workspace_prism_service.py tests/architecture/test_dataservice_boundaries.py -q
cd frontend && npm run test -- tests/unit/lib/latex-api.test.ts tests/unit/proxy.test.ts
cd frontend && npm run typecheck
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add backend/src backend/tests frontend
git commit -m "refactor: move latex api under prism adapter"
```

## Task 4: Current Docs And Final Guards

**Files:**
- Modify: `docs/current/architecture.md`
- Modify: `docs/current/workspace-current-state.md`
- Modify: `docs/current/frontend-feature-plugin-contract.md`
- Modify: `backend/tests/architecture/test_dataservice_boundaries.py`
- Modify/add frontend static guard tests

- [ ] **Step 1: Update docs**

Record:

- Auth returns Account DataService subject.
- Artifact runtime surface is WorkspaceArtifact, not legacy artifact.
- `/latex/*` is removed; Prism adapter route is the only backend manuscript adapter API.
- `/workspaces/{id}/prism` remains the only user-facing manuscript route.

- [ ] **Step 2: Run full verification**

Run:

```bash
cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/ -q
cd frontend && npm run typecheck
cd frontend && npm run build
```

Expected:

- Backend full suite PASS.
- Frontend typecheck PASS.
- Frontend build PASS.

- [ ] **Step 3: Commit docs and final guards**

```bash
git add docs backend/tests frontend/tests
git commit -m "docs: record runtime boundary convergence"
```

- [ ] **Step 4: Push master**

```bash
git push origin master
```
