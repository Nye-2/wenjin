# 10 Sandbox vNext Spec

Status: Implemented
Updated: 2026-07-15

Implementation outcome: typed Docker operation containers, pinned environments/images, path/network hardening, read-before-write, bounded outputs, manifests, receipts, and preflight are implemented. Production still must provide real rootless/userns, digest, quota, mount, and egress attestations.
Depends on: `09_permission_pause.md`, `07_review_commit_runtime.md`

## Goal

Keep Wenjin's sandbox as a research execution substrate, not a user-facing terminal. Docker/rootless operation containers are the single runtime implementation. Typed operations isolate the agent-facing contract from Docker internals; they are not a provider compatibility layer.

## Cutover Baseline

| Current file | Current responsibility | Target action |
|---|---|---|
| `backend/src/sandbox/base.py` | Sandbox interface and command execution | Keep provider interface; tighten typed operation defaults |
| `backend/src/sandbox/workspace_layout.py` | `/workspace` layout and path classification, including writable `.wenjin` under the broad mount | Redesign into public/control/environment roots and keep only the public virtual-path contract |
| `backend/src/sandbox/providers/docker.py` + `backend/src/execution/docker/client.py` | Runs a fresh container but mounts the whole workspace read/write; non-`none` profiles get ordinary network; no non-root/cap-drop/read-only/pids hardening | Replace container creation profile and mount topology; do not wrap weak defaults |
| `backend/src/agents/harness/sandbox_execution_tools.py` | `sandbox.run_python`, manifests, narratives | Move under ToolOrchestrator/SandboxRuntime |
| `backend/src/agents/harness/command_audit.py` | Command policy decision and network profile | Keep and make mandatory for sandbox operations |
| `backend/src/agents/harness/output_budget.py` | Externalized large outputs into internal refs | Keep; ensure MissionItem references bounded previews |
| `backend/src/agents/lead_agent/v2/sandbox_*` | Lead-owned sandbox runtime helpers | Move to SandboxRuntime, delete Lead ownership |

The table above records the deleted or reshaped pre-cutover paths; none is a current runtime authority.

## Provider

Canonical runtime:

```text
rootless Docker operation-container provider
```

Production requires a rootless daemon (or a separately reviewed equivalent such as userns-remap plus isolated worker host). Docker Desktop may be used for local development but does not satisfy the Linux production rootless release proof by itself.

Every operation container must enforce:

- non-root UID/GID, `cap_drop=ALL`, `no-new-privileges`, default/custom seccomp, and no privileged/devices/host namespaces.
- no Docker socket exposed inside task containers.
- read-only root filesystem, bounded tmpfs, explicit public workspace mounts, and no writable control-plane mount.
- no model keys, user API keys, or host secrets in container env.
- network profile enforced outside the model prompt/container process.
- hard CPU, memory+swap, pids, wall-time, output, and disk/quota limits.
- image digest pinning and environment manifest; no unreviewed runtime image drift.

Alternative sandbox providers are out of scope. Supporting one later requires an explicit architecture revision and clean cutover, not dormant adapters, provider enums, or dual paths. Docker-specific implementation fields still stay out of user-facing Mission output.

## Execution and Environment Model

Use short-lived operation containers and persistent content-addressed state:

```text
SandboxWorkspace   durable public files for a workspace
SandboxEnvironment immutable env_id = hash(image_digest + runtime + lockfile)
SandboxArtifactObject immutable sbxobj_<sha256> bytes in trusted control storage
SandboxJob         one bounded typed operation / container
```

- Do not keep a long-lived container/session as a second runtime owner. Container crash/removal cannot lose public files, sealed artifact bytes, dependency identity, or operation receipts.
- `sandbox.install_dependencies` is the only writer of an environment directory. It runs with `package_index_only`, produces a resolved lock + environment manifest, and seals the resulting env for read-only mounts in later jobs.
- A job mounts the selected environment read-only and writes only approved public output paths/tmpfs. Reproducibility records image digest, env id, lock hash, command schema version, and input hashes.
- Environment/workspace/job metadata stays in existing sandbox/asset domains and MissionItems; this design adds no mission table or long-lived container table.

## Layout

Canonical virtual root:

```text
/workspace/main
/workspace/datasets
/workspace/scripts
/workspace/outputs
/workspace/reports
/workspace/tmp
```

Host-side sandbox root separates untrusted public files from trusted control state:

```text
{sandbox_root}/public/**                 -> mounted under /workspace with per-path modes
{sandbox_root}/control/**                -> never writable or normally visible to task code
{sandbox_root}/environments/{env_id}/**  -> installer rw, later jobs ro under /opt/wenjin/env
```

Task scratch:

```text
/workspace/tmp/tasks/{mission_id}/{item_seq_or_subagent_id}
```

Mount policy:

```text
/workspace/datasets         read-only for compute jobs
/workspace/main             operation-specific read/write
/workspace/scripts          operation-specific read/write
/workspace/outputs          operation-specific read/write
/workspace/reports          operation-specific read/write
/workspace/tmp              bounded scratch/tmpfs
control/manifests/guidance  host-generated, never writable by untrusted code
```

Artifact and job manifests are computed by SandboxRuntime from hashes/receipts after execution. Untrusted code cannot self-declare a trusted manifest.

## Typed Operations

Default tools:

```text
sandbox.run_python
sandbox.run_notebook
sandbox.smoke_check
sandbox.install_dependencies
sandbox.register_dataset
sandbox.register_artifact
sandbox.read_artifact
sandbox.read_file
sandbox.read_output_ref
```

No free-form shell as default user mission tool.

Provider implementation note: a typed operation may compile to a shell command internally, but that shell string is not exposed as a user/agent capability. Every compiled command must pass CommandAuditPolicy and produce structured command metadata before execution.

Read-before-write is receipt-driven. The agent reads an existing stable script or output with `sandbox.read_file`, then submits complete replacement content. Mission tool handlers resolve the latest verified path/hash receipt and inject internal Sandbox preconditions; model-facing tool schemas expose neither base hashes nor output-hash maps. A stale receipt fails closed, and creating numbered/versioned paths to avoid the guard is not supported.

## Network Profiles

```text
none
package_index_only
explicit_egress_admin_only
```

Rules:

- default `none`
- dependency install uses `package_index_only`
- literature search uses model-native web search outside sandbox
- sandbox is not a fallback web-search provider
- deny local/private/metadata IP
- no model key or user API key in sandbox env
- `package_index_only` has no direct general internet route: DNS/HTTP(S) traverses an egress proxy with registry/domain allowlists, resolved-IP revalidation, and private/loopback/link-local/metadata denial. Docker bridge selection or prompt instructions alone are not enforcement.

## Manifest Requirements

Artifact:

```text
path
kind
content_hash
source_script
dataset_paths
sandbox_environment_id
sandbox_job_id
mission_id
item_seq
network_profile
stdout_truncated
stderr_truncated
created_at
```

Dataset:

```text
dataset_id
source
source_hash
license
pii_risk
uploaded_by
observed_at
used_by_artifacts
```

No manifest means no save.

## Output Handling

- stdout/stderr bounded head/tail preview.
- full output externalized as internal output ref.
- internal refs cannot be listed, searched, registered, or committed.
- failure keeps recovery guidance and bounded logs.
- nonzero exit is structured tool result, not raw exception.

## Review Boundary

Sandbox can only stage candidates:

```text
ArtifactManifest
ResearchToolOutcome
sealed SandboxArtifactObject
```

The WorkspaceAgent may use those receipts as evidence or source refs for an internal candidate. Only a stage-accepted candidate can later become a MissionReviewItem. Sandbox never creates user-review state or directly commits rooms.

Mission linkage:

- Sandbox jobs store `mission_id` and optional `mission_item_seq`.
- Sandbox dispatch and terminal receipts carry a stable operation key plus the current mission lease epoch; duplicate queue delivery cannot create a second billable effect.
- `execution_id` and `execution_node_id` are removed from sandbox job/lease/artifact contracts.
- A ChatTurnRun may request a sandbox-backed mission action only through MissionRuntime; it never owns a sandbox job.

## Untrusted Input Delegate

External pages, papers, repos, and prompt-like pasted text should be read by restricted delegate:

```text
read-only
no shell
no write
no network escalation
structured JSON output
prompt-injection neutralization
```

## Tests

- Docker/rootless provider creates canonical layout.
- Production preflight rejects a rootful/unhardened daemon profile; local dev override is explicit and cannot pass release gates.
- Containers run non-root with all capabilities dropped, no-new-privileges, read-only root, pids/CPU/memory+swap/time limits, no devices/ports, and pinned image digest.
- Free shell is unavailable in default mission.
- Network default denies external and local/private/metadata IP.
- `package_index_only` cannot access arbitrary web.
- Trusted control/manifests are not reachable through the writable public workspace mount and cannot be forged by task code.
- Dependency environment survives operation-container removal, is content-addressed, and is mounted read-only after sealing.
- Every produced reviewable artifact is copied once into `control/artifact_objects/sbxobj_<sha256>.bin`; receipts read that immutable object rather than the mutable public path.
- Artifact without manifest cannot become MissionReviewItem.
- Internal output ref cannot be registered as artifact.
- Read-before-write required for existing file patch.
- Symlink escape rejected.
- Nonzero Python exit returns structured recovery guidance.
- Provider shell execution, if used internally, is unreachable without typed operation and command audit metadata.
- Duplicate operation keys reuse or report the existing sandbox job instead of executing twice.
