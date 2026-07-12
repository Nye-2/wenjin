# Mission Policy and Worker Skill Catalog

> Status: Current source of truth
> Updated: 2026-07-11

## Principle

Wenjin constrains outcomes and boundaries, not every internal step. The model receives a goal, high-quality examples, strict acceptance contracts, and a limited tool surface; the agent loop remains free to plan, delegate, critique, and revise.

The catalog has exactly two runtime entities:

- **MissionPolicy**: workspace-scoped contract for what a mission must achieve and which boundaries apply;
- **WorkerSkill**: reusable guidance for how a subagent can perform a class of work well.

Neither entity is a user-facing workflow button. Neither creates a fixed team graph.

## DataService SSOT

| Table | Key | Content |
|---|---|---|
| `mission_policies` | `(workspace_type, id)` | schema version, enabled flag, policy JSON, content hash, source path |
| `worker_skills` | `id` | schema version, enabled flag, skill JSON, content hash, source path |

The loader exposes typed list/get/has/load operations. Content hashes make policy and skill snapshots auditable. Mission creation pins the selected policy hash; running missions are not silently changed by a later catalog deployment.

## MissionPolicy

A policy defines:

- identity, workspace type, title, description, and examples;
- completion targets and required stage sets;
- resolved `StageAcceptanceContract`s;
- allowed tool groups and permission/network boundaries;
- suggested worker skills;
- review defaults and protected output classes;
- model effort and budget/iteration bounds;
- user-input requirements and graceful capability-gap behavior.

The policy must not prescribe a fixed sequence of named agents or a giant prompt script. Stages express quality dependencies, not UI steps.

Current workspace families include SCI research, thesis, proposal, software copyright, math modeling, and patent work. Each family may expose several mission policies, but users reach them through ordinary chat intent.

## StageAcceptanceContract

Each contract belongs to one policy and stage. It defines minimum/excellent criteria, required evidence and artifacts, blockers, review requirements, permitted next stages, iteration limit, and minimum reasoning effort. Runtime assessments cite current candidate refs and are evaluated deterministically.

Examples:

- SCI topic positioning must produce a defensible question, literature-backed gap, feasible contribution, and explicit limitations before method design;
- math modeling question one must pass formulation, assumptions, computation, validation, and explanation before question two starts;
- patent claims must remain supported by disclosure and avoid introducing unsupported scope.

## WorkerSkill

A skill is compact, composable worker guidance:

- purpose and when to use it;
- required inputs and structured outputs;
- excellent examples and anti-examples;
- method checklist and stop conditions;
- suggested tool groups;
- evidence, safety, and citation constraints.

Skills do not grant tools. The pinned MissionPolicy resolves the actual tool ids, and the main agent may narrow a subagent further. A subagent may use multiple skills if their contracts do not conflict.

## Tool groups

The canonical groups are resolved against the frozen production ToolCatalog:

| Group | Purpose |
|---|---|
| `model_native_web_search` | cited provider-native research search |
| `workspace_read` | workspace assets, documents, and indexed source text |
| `source_import` | import verified source candidates into the Library |
| `source_code_read` | bounded software-project source reads |
| `sandbox_compute` | Python/notebook/smoke checks, dependencies, manifests, output reads |
| `artifact_render` | create reviewable artifact candidates |
| `draft_stage` | port-backed atomic review candidates |

Unknown groups fail deployment/runtime validation. A known group whose provider capability is unavailable becomes an explicit capability gap; policy decides whether to pause, degrade, or fail closed.

## Loading and change process

1. Validate seed schema and cross references.
2. Resolve and validate all stage contracts and tool groups.
3. Write catalog records through DataService with content hashes.
4. Probe the selected model/tool capabilities.
5. Start a Mission only after the policy can be pinned completely.

Catalog updates are code-reviewed deployments. There is no runtime admin form that can bypass validation. During development, incompatible records are dropped/reseeded rather than maintained through aliases.

## Invariants

1. MissionPolicy is the only mission methodology/policy SSOT.
2. WorkerSkill is guidance, not orchestration or permission.
3. StageAcceptanceContract is the only stage quality contract.
4. ToolCatalog is the only tool registration SSOT.
5. A running mission uses pinned hashes and exact tool ids.
6. No fixed team template, workflow graph, or legacy catalog is accepted.
