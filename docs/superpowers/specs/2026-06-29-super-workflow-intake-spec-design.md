# Super Workflow Intake Spec for Software Copyright and Math Modeling

## Goal

Turn the two priority one-shot workspaces into a spec-first workflow:

- `software_copyright`: the Chat Agent guides the user from a vague software idea to an executable software copyright application spec.
- `math_modeling`: the Chat Agent guides the user from a contest problem to an executable CUMCM paper-pack spec.

The product promise is not "click a capability and answer a generic missing-field question." The promise is:

1. Chat collects and sharpens the minimum viable task definition.
2. Chat writes a human-readable Markdown execution spec and a structured JSON params payload.
3. The user can inspect the spec in chat and in the right workbench preview.
4. Execution starts only through the existing capability pipeline, using that same spec as input.

The final execution chain remains:

`Chat Agent -> launch_feature -> ExecutionRecord -> Lead Agent / TeamKernel -> ResultCard / Prism / rooms`

No bypass router, no separate workflow engine, and no second execution stream should be introduced.

## Product Decision

Use an `IntakeSpecV1` contract for super workflows.

The Chat Agent owns intake, clarification, and spec writing. The Lead Agent owns execution after launch. The right workbench owns preview, confirmation, and execution visibility.

There are two valid launch paths:

| Launch path | Owner | Required input | Behavior |
| --- | --- | --- | --- |
| Chat launch | Chat Agent | Latest ready `IntakeSpecV1` + clear user intent such as "开始做" | Chat calls `launch_feature` with `params` from the spec. |
| Workbench launch | Right workbench | Latest ready `IntakeSpecV1` selected by the user | Frontend sends a message/action that carries `orchestration.feature_id` and `orchestration.params`, then existing auto-launch starts the capability. |

Both paths must produce the same execution payload. The only difference is whether the user's final confirmation comes from chat text or the right-side button.

## Non-Goals

- Do not redesign the home page.
- Do not replace the two-agent topology.
- Do not add a new public workspace type.
- Do not add an eighth chat block type in the first slice.
- Do not make a generic form builder for every capability.
- Do not ask the user to choose model providers, image engines, sandbox settings, or internal agent stages.
- Do not make software copyright produce a production-grade full-stack application.
- Do not let the right-side button call Lead Agent directly.

## User Experience

### Software Copyright First-Run Shape

When the user enters a software copyright workspace or clicks `软著申请材料包`, the product should feel like a guided application-prep desk.

The Chat Agent should ask compact, concrete questions:

1. 你想做一个什么软件？
2. 软件名称是什么？如果没有，我可以按用途帮你起一个申报风格的名称。
3. 交付形态是什么？
   - Web 管理系统: simplest and most stable for screenshots and materials.
   - App static prototype: suitable when the idea is mobile-first; screenshots use mobile viewport.
   - Mini-program static prototype: suitable for light service flows; screenshots use mobile viewport.
   - Desktop static prototype: suitable for tools and internal systems; screenshots use desktop viewport.
   - 系统建议: default to Web unless the user's idea clearly needs mobile.
4. 技术栈偏好是什么？
   - Java/Spring-style backend mock.
   - Python/FastAPI-style backend mock.
   - Node/Express-style backend mock.
   - 系统建议.
5. 面向谁使用？
6. 核心功能模块有哪些？用户可以填 "你帮我生成"。
7. 有没有必须强调的场景、行业、合规点或功能？

After enough context is available, Chat writes a spec card:

```text
我将为你生成一个名为「...」的软件著作权申请材料包。
形态采用 ...，后端生成 mock 代码，前端生成静态页面并用浏览器截图。
材料包括申请表填报素材、软件说明书、功能模块说明、材料清单、代码/截图证据说明和架构图。
还有什么一定要强调的吗？
```

If the user replies with a change, Chat updates the spec. If the user says "开始做" or clicks the right-side button, the capability launches.

### Math Modeling First-Run Shape

When the user enters a math modeling workspace or clicks `数学建模论文包`, the product should feel like a contest-paper production desk.

The Chat Agent should ask only the questions that affect execution:

1. 请上传或粘贴赛题题面。截图可以先上传，系统后续做 OCR or text extraction where available.
2. 是否有数据附件？如果没有，系统按题面构造可说明的示例/占位数据策略，但必须标明。
3. 竞赛格式是什么？
   - 默认 CUMCM / 高教社杯.
   - 校赛 or other contest if the user says so.
4. 目标是什么？
   - 完整论文包.
   - 建模思路.
   - 代码和图表.
   - 全部.
5. 风格偏好是什么？
   - 稳妥拿奖.
   - 创新一点.
   - 系统建议.
6. AI 使用声明要求是否已知？

Do not ask for programming language. Math modeling execution always uses Python.

After enough context is available, Chat writes a spec card:

```text
我将按 CUMCM 风格为这道题生成论文包。
求解和绘图统一使用 Python，输出可复现脚本、结果表、图表、LaTeX 初稿和格式检查说明。
如果附件缺失，我会在论文和支持材料中显式标明假设与数据限制。
还有什么一定要强调的吗？
```

## IntakeSpecV1 Contract

### Purpose

`IntakeSpecV1` is the bridge between conversational clarification and deterministic capability execution.

It has two forms:

- Markdown: user-facing spec preview.
- JSON params: canonical `launch_feature.params` input.

Both must be generated from the same source facts. The Markdown preview must not claim anything absent from the JSON params or workspace materials.

### Schema

```json
{
  "schema_version": "wenjin.intake_spec.v1",
  "spec_id": "intake-...",
  "workspace_id": "workspace-...",
  "workspace_type": "software_copyright",
  "capability_id": "software_copyright_application_pack",
  "status": "draft | ready | launched",
  "title": "软著申请材料包执行 Spec",
  "markdown": "# ...",
  "params": {},
  "missing_fields": [],
  "assumptions": [],
  "created_from_message_id": "msg-...",
  "updated_from_message_id": "msg-...",
  "revision": 1
}
```

Required fields:

- `schema_version`
- `spec_id`
- `workspace_id`
- `workspace_type`
- `capability_id`
- `status`
- `title`
- `markdown`
- `params`
- `missing_fields`
- `assumptions`
- `revision`

Status rules:

- `draft`: important context is still missing or the user is still changing the brief.
- `ready`: all required execution fields are present or safely assumed and disclosed.
- `launched`: an execution has been started from this spec revision.

### Software Copyright Params

```json
{
  "software_name": "智慧校园活动管理系统",
  "software_short_name": "活动管理系统",
  "version": "V1.0",
  "software_form": "web",
  "backend_mock_stack": "java_spring",
  "frontend_static_strategy": "desktop_web",
  "target_users": "高校活动管理员、学生社团负责人、学生用户",
  "application_scenario": "校园活动发布、报名、审核、签到和统计",
  "function_modules": [
    "用户登录与权限管理",
    "活动发布与审核",
    "报名管理",
    "签到核销",
    "数据统计报表"
  ],
  "deliverable_scope": [
    "application_form_material",
    "software_manual",
    "function_module_description",
    "mock_backend_source",
    "static_frontend_prototype",
    "prototype_screenshots",
    "architecture_diagrams",
    "submission_checklist"
  ],
  "visual_strategy": {
    "ui_screenshots": "playwright_static_frontend",
    "diagrams": "mermaid_or_graphviz",
    "llm_images": "forbidden_for_evidence"
  },
  "source_strategy": {
    "backend": "mock_source_for_deposit_narrative",
    "frontend": "static_pages_for_screenshots",
    "runtime": "sandbox_static_build_or_static_server"
  },
  "constraints": "不要声称已经上线生产；截图标记为本地原型证据。"
}
```

Implementation defaults:

- If `software_form` is absent, default to `web`.
- If `backend_mock_stack` is absent, default to `java_spring` for Chinese software copyright style unless user prefers Python/Node.
- If the user asks for App, Mini Program, or desktop, still generate static frontend pages and screenshot them at the corresponding viewport.
- Do not require a real database, mobile SDK, app build chain, mini-program IDE, or desktop packaging chain.

### Math Modeling Params

```json
{
  "problem_statement": "赛题题面文本或 OCR 摘要",
  "data_assets": "已上传附件说明或缺失说明",
  "target_format": "CUMCM / 高教社杯",
  "goal": "完整论文包",
  "modeling_style": "稳妥拿奖",
  "programming_language": "python",
  "deliverable_scope": [
    "problem_analysis",
    "model_assumptions",
    "python_solver_scripts",
    "result_tables",
    "code_generated_figures",
    "latex_paper_draft",
    "supporting_materials_manifest",
    "format_check_report",
    "ai_use_disclosure"
  ],
  "visual_strategy": {
    "data_figures": "python_matplotlib_seaborn_plotly_static",
    "method_diagrams": "mermaid_graphviz_tikz_or_python_schematic",
    "llm_images": "forbidden_for_evidence"
  },
  "sandbox_strategy": {
    "language": "python",
    "scripts_dir": "/workspace/scripts",
    "outputs_dir": "/workspace/outputs",
    "figures_dir": "/workspace/outputs/figures/math_modeling"
  },
  "constraints": "如数据缺失，必须显式写明假设与限制。"
}
```

Implementation defaults:

- `programming_language` is always `python`.
- Do not ask the user about MATLAB, R, Julia, C++, or solver language in the first-run intake.
- Use Python for data cleaning, model solving, result tables, and all evidence charts.
- Evidence charts must be code-generated and reproducible.

## Chat Agent Behavior

### Intake Mode

The Chat Agent enters intake mode when:

- the current workspace type is `software_copyright` or `math_modeling` and the user asks for the primary super workflow;
- the user clicks the corresponding right-side capability entry;
- the URL/deep-link carries the corresponding capability id;
- the user says a direct intent such as "我要办软著" or "我把数模题发给你直接写".

In intake mode, the Chat Agent should:

1. Ask compact, domain-specific questions.
2. Accept incomplete answers and infer defaults when safe.
3. State assumptions explicitly.
4. Produce or update `IntakeSpecV1`.
5. Avoid launching until the spec is `ready` and the user has confirmed execution.

### Launch From Chat

The Chat Agent may call `launch_feature` when all are true:

1. Latest spec is `ready`.
2. The user's latest message expresses clear execution intent.
3. The capability id matches the latest spec.
4. The tool call uses `params` copied from the latest spec, not a newly improvised short summary.

Examples of launch intent:

- "开始做"
- "没问题，执行"
- "按这个来"
- "可以，直接生成"
- "go ahead"

Examples that should not launch:

- "这里的软件名换一下"
- "我还想加一个模块"
- "这个方案靠谱吗？"
- "先别做，我看看"

### Clarification Rules

For software copyright:

- Missing software idea or software name should trigger a question.
- Missing programming stack should not block execution; use default and disclose.
- Missing modules should not block execution if the user authorizes system generation.
- Missing legal ownership facts should be marked as user-confirmation assumptions, not invented.

For math modeling:

- Missing or unreadable problem statement blocks execution.
- Missing data attachments do not always block execution; the spec must state the limitation.
- Missing programming language never blocks because Python is fixed.
- Unknown AI-use policy should become a disclosed assumption or a question if the user says the contest has special rules.

## Intake Spec Creation Tool

### Why A Tool Is Needed

The first slice should not rely on the language model directly mutating assistant-message metadata. The Chat Agent's durable output contract is block-oriented, and frontend history hydration already understands persisted blocks.

Add a built-in Chat Agent tool:

```python
draft_intake_spec(
    capability_id: str,
    workspace_type: str,
    title: str,
    markdown: str,
    params: dict,
    status: Literal["draft", "ready"],
    missing_fields: list[str] = [],
    assumptions: list[str] = [],
)
```

The tool validates `IntakeSpecV1` and returns:

```json
{
  "status": "ready",
  "intake_spec": {
    "schema_version": "wenjin.intake_spec.v1",
    "...": "..."
  }
}
```

This result travels through the existing `tool_invocation` and `tool_result` block protocol. `MessageBlock` can render a custom `IntakeSpecCard` when it sees a `tool_result` whose output contains `intake_spec`.

Optional optimization: `thread_turn_handler` may mirror the latest `intake_spec` into assistant-message metadata for faster lookup, but the first-slice source of truth should be the persisted tool result block.

### Tool Rules

- The tool does not launch anything.
- The tool does not write Prism files.
- The tool may persist the spec only inside the conversation block stream in the first slice.
- The tool must reject invalid specs instead of returning a half-usable card.
- The tool must normalize defaults such as math modeling `programming_language: "python"`.
- The tool must preserve the exact `params` object that should later go into `launch_feature`.

## Frontend Workbench Design

### Chat Card

Do not add a new block type in the first slice.

`ChatPanel` projects a `tool_result` containing `output.intake_spec` as an `IntakeSpecCard` inside that assistant message. If message metadata also contains `intake_spec`, the frontend may use it as a cache, but the tool result remains authoritative.

The card displays:

- spec title;
- status: `草稿` / `可执行` / `已启动`;
- 3 to 5 key facts;
- missing fields, if any;
- actions:
  - `查看 Spec`;
  - `修改/补充`;
  - `同意，开始执行` when status is `ready`.

The card should be compact and not look like a raw log. It should use current `--wjn-*` tokens.

### Right-Side Preview

The right workbench gets a new projection state: `intake_spec_preview`.

When a user clicks `查看 Spec` in chat or when a ready spec exists and no run is active, the right panel shows:

- a header with spec title and status;
- Markdown rendered preview;
- a small assumptions/missing-fields section;
- primary button `同意，开始执行`;
- secondary button `回到工作台`.

The preview should feel like a document pane, not a modal. It should support ordinary Markdown syntax:

- headings;
- bullet lists;
- tables;
- code blocks;
- inline code;
- blockquotes.

Use the existing Markdown renderer if it is safe for this surface. If not, create a small bounded renderer for the preview and disallow raw HTML.

### Workbench States

| State | Right panel behavior |
| --- | --- |
| No spec, no run | Show primary capability entry and a note: "先在左侧完成任务设定，或点击能力开始设定." |
| Spec draft | Show clarification progress, missing fields, and preview button. |
| Spec ready | Show Markdown preview and `同意，开始执行`. |
| Launching/running | Switch to existing run view. |
| Completed | Use existing result card and commit flow. |

### Right Button Launch

The right-side launch button should not call a new execution API.

It should send a thread message or block action equivalent to:

```json
{
  "content": "同意，开始执行这份 Spec。",
  "metadata": {
    "orchestration": {
      "feature_id": "software_copyright_application_pack",
      "params": {
        "...": "copied from IntakeSpecV1.params"
      }
    },
    "intake_spec_launch": {
      "spec_id": "intake-...",
      "revision": 3
    }
  }
}
```

Existing `CapabilityAutoLaunchMiddleware` can then launch deterministically from metadata. This preserves the Chat Agent to Lead Agent boundary.

The frontend should copy `params` from the selected `IntakeSpecV1` object exactly. It must not reconstruct params from rendered Markdown.

## Backend Design

### Contract Module

Add backend and frontend types for `IntakeSpecV1`.

Backend candidate:

`backend/src/agents/contracts/intake_spec.py`

Frontend candidate:

`frontend/lib/intake-spec.ts`

The contract should validate:

- known `workspace_type`;
- supported `capability_id`;
- `params` includes required minimum fields for that workspace;
- math modeling `programming_language` is exactly `python`;
- software copyright visual strategy forbids AI evidence screenshots;
- Markdown is non-empty and bounded.

### Tool Result And Metadata Transport

The primary transport is an existing tool-result block:

```json
{
  "kind": "tool_result",
  "tool": "draft_intake_spec",
  "status": "ready",
  "output": {
    "intake_spec": {
      "schema_version": "wenjin.intake_spec.v1",
      "...": "..."
    }
  }
}
```

Assistant-message metadata may optionally mirror the latest spec:

```json
{
  "intake_spec": {
    "schema_version": "wenjin.intake_spec.v1",
    "...": "..."
  }
}
```

User confirmation messages include:

```json
{
  "intake_spec_launch": {
    "spec_id": "...",
    "revision": 1
  },
  "orchestration": {
    "feature_id": "...",
    "params": {}
  }
}
```

Thread history should persist these metadata fields. Frontend should hydrate the latest spec from history, not only from live SSE events.

Frontend hydration should scan, in order:

1. persisted `tool_result` blocks with `output.intake_spec`;
2. assistant metadata `intake_spec` mirror, if present.

The latest higher `revision` for the same `spec_id` wins.

### Prompt Changes

Update Chat Agent routing prompt for the two super workflows:

- clicking a primary super workflow should start/continue intake, not immediately launch;
- when a draft or ready spec needs to be shown, call `draft_intake_spec`;
- `launch_feature` is allowed after spec ready and explicit confirmation;
- when launching, pass the latest spec params unchanged;
- do not expose internal route-card ids unless needed in metadata/tool calls.

The generic rule "clicked capability means launch" should be narrowed:

- ordinary capabilities can keep current launch behavior;
- `software_copyright_application_pack` and `math_modeling_paper_pack` use spec intake behavior.

### Auto Launch Middleware

Keep `CapabilityAutoLaunchMiddleware` for explicit right-side confirmation.

Add a guard so a workbench click can request intake instead of launch:

```json
{
  "workbench_launch": {
    "capability_id": "software_copyright_application_pack",
    "mode": "intake"
  }
}
```

`_extract_launch_feature_id_from_metadata` should ignore `workbench_launch` when `mode == "intake"`.

This prevents the current behavior where clicking the card immediately calls `launch_feature` before a spec exists.

### Launch Feature Params

When `orchestration.params` is present, keep the current normalization path:

- strip reserved UI keys;
- pass the remaining object to `launch_feature_params`;
- let `build_execution_launch_params()` wrap it as `TaskBrief.brief`.

Add tests to ensure nested `IntakeSpecV1.params` survives unchanged.

## Capability Seed Changes

### Software Copyright

Update `software_copyright_application_pack.yaml`:

- stronger `routing.user_guidance` that says intake produces a spec before execution;
- `minimum_context` should remain `software_name: required`, but intake can generate a provisional name if the user explicitly allows it;
- `brief_schema` should include the software copyright params listed above;
- graph prompts should reference:
  - mock backend source generation;
  - static frontend prototype generation;
  - Playwright screenshot evidence;
  - no production deployment claims.

Quality gates should include:

- `intake_spec_required_for_super_workflow`;
- `mock_code_and_static_screenshot_consistency`;
- `prototype_screenshots_marked_when_not_real`;
- `no_ai_generated_evidence_screenshots`;
- `software_name_version_consistent`.

### Math Modeling

Update `math_modeling_paper_pack.yaml`:

- remove any user-facing implication that language is configurable;
- default `programming_language: python`;
- graph prompts should require Python scripts for solver, charts, tables, and reproducibility commands;
- clarification prompt should ask for problem statement and attachments, not language.

Quality gates should include:

- `intake_spec_required_for_super_workflow`;
- `python_solver_required`;
- `figure_scripts_reproducible`;
- `no_ai_generated_data_figures`;
- `cumcm_structure_and_format_checked`.

## Execution Behavior

### Software Copyright Execution

The Lead Agent should treat the spec as the execution brief.

Expected production line:

1. Software structure planner creates name/version/module consistency matrix.
2. Mock code generator creates backend source files for source-deposit narrative.
3. Static prototype generator creates frontend pages.
4. Screenshot runner builds or serves static pages and captures browser screenshots.
5. Diagram generator creates architecture/module/flow diagrams via Mermaid, Graphviz, or TikZ.
6. Document drafter writes application-form material, manual, module explanation, and checklist.
7. Review critic checks consistency and evidence labeling.

Implementation constraints:

- backend code can be mock code;
- frontend can be static HTML/CSS/JS or a lightweight static build;
- screenshots must come from rendered static pages;
- do not require database, login backend, mobile SDK, mini-program IDE, native app packaging, or cloud deployment.

### Math Modeling Execution

The Lead Agent should treat the spec as the execution brief.

Expected production line:

1. Problem parser extracts tasks, variables, constraints, data assets, and missing inputs.
2. Modeling planner designs assumptions, objective functions, constraints, algorithms, validation, and sensitivity analysis.
3. Python solver creates reproducible scripts and result tables.
4. Figure/table engineer creates code-generated charts and tables.
5. Paper drafter writes the CUMCM-style LaTeX paper.
6. Compliance reviewer checks format, page structure, support materials, and AI-use declaration.

Implementation constraints:

- Python is fixed;
- data figures are code-generated;
- missing data is disclosed;
- all result claims must cite scripts, tables, or generated artifacts where applicable.

## Testing Plan

### Backend Unit Tests

- `IntakeSpecV1` validates software copyright ready specs.
- `IntakeSpecV1` validates math modeling ready specs.
- Math modeling rejects non-Python `programming_language`.
- Software copyright rejects `llm_image` as evidence screenshot strategy.
- `draft_intake_spec` returns a validated `tool_result` payload with `output.intake_spec`.
- Invalid `draft_intake_spec` payloads return a visible advisory instead of a ready spec.
- Metadata extraction ignores `workbench_launch.mode == "intake"`.
- Metadata extraction still launches when `orchestration.feature_id` and `orchestration.params` are present.
- `build_execution_launch_params()` preserves nested spec params.

### Chat Agent Tests

- Clicking software copyright primary capability produces intake guidance, not immediate launch.
- Clicking math modeling primary capability produces intake guidance, not immediate launch.
- With a ready spec and user says "开始做", Chat calls `launch_feature` using spec params.
- If the user changes a field after ready spec, Chat updates the spec instead of launching.

### Frontend Unit Tests

- ChatPanel renders `IntakeSpecCard` from `draft_intake_spec` tool results.
- Right workbench finds the latest spec from hydrated tool-result history.
- Markdown preview renders headings, lists, tables, code blocks, and inline code.
- Start button sends `orchestration.feature_id` plus exact `params`.
- Spec draft state disables start button and shows missing fields.

### Browser Smoke Tests

Run after implementation:

1. Create/open software copyright workspace.
2. Click `软著申请材料包`.
3. Verify no execution starts immediately.
4. Answer intake questions.
5. Verify spec card appears in chat.
6. Open right preview.
7. Click `同意，开始执行`.
8. Verify `launch_feature` starts and run view appears.
9. Repeat for math modeling, verifying Python is fixed and not asked as a question.
10. Test mobile 390x844 for card and preview readability.

## Rollout Plan

Phase 1: Contract and transport

- Add `IntakeSpecV1` backend/frontend types.
- Add `draft_intake_spec` built-in Chat Agent tool.
- Add metadata extraction and latest-spec helpers.
- Add middleware guard for `workbench_launch.mode == "intake"`.

Phase 2: Frontend projections

- Add `IntakeSpecCard` in ChatPanel.
- Add right-side Markdown preview state.
- Add `同意，开始执行` action using existing send-message path.

Phase 3: Chat prompt and seeds

- Update Chat Agent prompt for super workflow intake.
- Update software copyright and math modeling capability YAML.
- Add tests for no immediate launch on intake click.

Phase 4: Execution quality constraints

- Strengthen soft copyright prompts for mock backend, static frontend, screenshots, and evidence labeling.
- Strengthen math modeling prompts for Python-only solver and reproducible charts.

Phase 5: Smoke and polish

- Redeploy.
- Browser-test desktop and mobile.
- Verify no console errors, no blank previews, and execution starts through existing pipeline.

## Acceptance Criteria

Software copyright:

- Clicking `软著申请材料包` starts intake instead of immediate generic launch.
- The user can provide a software idea and name through chat.
- Chat produces a ready spec card.
- Right preview shows the full Markdown spec.
- Right button launches the capability with spec params.
- Chat text "开始做" also launches the same spec.
- Execution params include mock backend and static frontend screenshot strategy.

Math modeling:

- Clicking `数学建模论文包` starts intake instead of immediate generic launch.
- Chat asks for problem statement and attachments, not programming language.
- Ready spec always includes `programming_language: "python"`.
- Right preview shows the full Markdown spec.
- Right button launches the capability with spec params.
- Chat text "开始做" also launches the same spec.

Shared:

- No new chat block type is required in this slice.
- Spec cards are projected from existing `tool_result` blocks.
- No direct right-panel-to-Lead-Agent bypass exists.
- Existing result_card commit flow remains unchanged.
- Existing run view remains the execution state surface.
- History reload restores the latest spec card and preview state.

## Self-Review

### Placeholder Scan

No placeholder fields are left for future decision. Open implementation details are expressed as candidate file paths or phased tasks, not unresolved product requirements.

### Consistency Check

The design consistently keeps Chat Agent as the intake owner and Lead Agent as the execution owner. Both chat launch and right-button launch converge on `launch_feature` with the same `IntakeSpecV1.params`.

### Scope Check

The first slice is limited to the two priority super workflows. It deliberately avoids a generic form builder and avoids adding a new block type.

### Ambiguity Check

The most important ambiguity is resolved explicitly: the right panel may start execution, but only by sending orchestration metadata through the existing chat/auto-launch path. It does not call Lead Agent directly.

### Optimization Notes

The design uses existing tool-result blocks for first-slice speed and compatibility. A later hardening pass can persist specs as first-class workspace documents if spec versioning, diffing, or multi-spec history becomes important.
