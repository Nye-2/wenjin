# Mission Runtime Open Questions Decision Pack

Status: Implementation resolved; one deployment capability decision pending
Updated: 2026-07-11
Overview: [`mission-runtime-overview.md`](mission-runtime-overview.md)

This companion contains only questions that survived the code/doc/live-contract fact gate. Implementation details already decided by evidence stay in the overview or owning spec.

## 1. OQ1: Native Web Search Runtime

### OQ1-native-web-search-runtime

**回链 / Backlink**: [Overview Section 13](mission-runtime-overview.md#13-open-questions).

**Overview anchors**: OQ1; Project Map S9/S11 and D2; locked decisions D18/D21; durable dispatch and model-capability release gates; `12_tool_orchestrator.md` and `13_migration_release_gate.md`.
**Question class**: external dependency plus owner rollout decision.
**Decision needed**: 当前独立 Responses SSE adapter 已能在验证完成边界主动关闭流；部署时 provider 是否能持续返回完整 search/source/citation receipts？若 probe 失败，是否接受搜索型 Mission 暂不开放？
**Why it matters**: 文献定位、研究空白、引用核验和实时资料任务不能把模型自报 URL 当作检索证据。
**Impact scope**: Model Catalog、ToolOrchestrator、search runtime、SCI/thesis StageAcceptanceContract、release gate。

**Fact gate result**:

| Candidate fact | Can current workspace decide it? | Action taken | Result |
|---|---|---|---|
| 当前实现是否调用真正的 hosted web search | yes | local code: `backend/src/services/search/model_native.py`, `backend/src/mission_runtime/production.py` | Yes. It uses an independent Responses SSE `web_search` tool and rejects missing receipts. |
| 当前发布模型是否支持标准 structured function calls | yes | redacted live contract probe against configured endpoint, 2026-07-10 | `gpt-5.5` Chat Completions returned the forced function name and schema-valid JSON args, emitted `[DONE]`, and closed without transport error. |
| 当前模型是否真的执行 native web search | yes | redacted live probe against root `/responses`, 2026-07-10 | Yes at the semantic layer: the stream emitted `web_search_call` lifecycle events, a completed search action with 36 sources, a URL citation annotation, and `response.completed`. |
| Responses 是否满足生产传输合同 | yes | OpenAI SDK, raw HTTP/1.1, and curl HTTP/2 probes, 2026-07-10 | No. After `response.completed`, HTTP/1.1 ended with incomplete chunked read and HTTP/2 ended with `INTERNAL_ERROR`; the official SDK surfaced the same transport exception. |
| 稳定的 Chat Completions 是否能提供可验证搜索回执 | yes | `web_search_preview` and `web_search_options` probes against `gpt-5.5`, 2026-07-10 | No structured search call, annotations, or sources were returned. A model-authored URL is not a search receipt. |
| 当前 relay 是否提供专用 Chat Completions search model | yes | redacted probe of `gpt-5-search-api`, 2026-07-10 | `404 model_not_found`. |
| 官方新集成协议是什么 | yes | OpenAI official web-search guide | Responses API with `web_search`; required tool choice when search must execute; citations/sources come from provider structured output. |
| relay 修复时间与部署版本 | owner-only | cannot be derived from repo | Pending relay owner/infra confirmation. |

**Known evidence**:

| Fact | Source | Confidence | Overview anchor | Implication |
|---|---|---|---|---|
| Model Catalog now stores generation API plus versioned profile/probe evidence and hash. | local code: `backend/src/database/models/model_catalog.py`, migration 087 | code fact | S11/D21 | Capability is proven and invalidated on endpoint/model/API drift. |
| Native search parser requires provider search lifecycle, sources, citations, and completed response. | local code: `backend/src/services/search/model_native.py` | code fact | S9/D21 | Unit coverage enforces structure, while live probe remains release evidence. |
| Chat Completions web search is limited to specialized search models; new integrations should use Responses `web_search`. | [OpenAI Web search guide](https://developers.openai.com/api/docs/guides/tools-web-search) | official doc fact | D18/D21 | Current generic Chat payload is not a valid capability proof. |
| User previously locked runtime search to model-native web search and rejected Semantic Scholar/other fallbacks. | user confirmation in this thread | user-confirmed | D18 | Reintroducing old providers is not a valid silent fallback. |

**Candidate options**:

| Option | Description | Pros | Risks |
|---|---|---|---|
| A | Repair or upgrade the current relay so `gpt-5.5` Responses preserves its existing structured search receipts and also closes HTTP/1.1 and HTTP/2 streams cleanly. Re-probe before enabling it. | Keeps one model/provider and restores model-native research search without an adapter workaround. | Depends on relay ownership and timeline; semantic success alone is insufficient. |
| B | Ship the stable Chat Completions baseline without web search; literature stages pause or return evidence-limited partial output. | No dual protocol, hidden model, or malformed-stream compatibility code. | Core SCI/thesis promise is materially weakened; many quality contracts cannot pass. |

**Current leaning**: keep the implemented split: Chat Completions for generation and a separate, receipt-verified Responses SSE search tool. Search-required policies fail closed whenever the live profile is unavailable; there is no provider fallback.
**Owner decision still needed**:

- Confirm the deployment probe passes; otherwise explicitly accept that search-required Mission policies remain unavailable for that release.

**Blocked evidence, if any**:

- The repository cannot determine the relay fix timeline or deploy a server-side HTTP framing repair.

**Decision owner**: Wenjin product/infra owner.
**Affected docs**: Overview Sections 5, 7, 10, 11, 13; `12_tool_orchestrator.md`; `13_migration_release_gate.md`; model catalog seed/config docs.
**Blocking scope**: implementation is complete; only search-dependent release acceptance is blocked.
**Write-back rule**: record the deployment probe hash/evidence or explicit no-search release scope in the model catalog and release record, then close OQ1.

## Decision Convergence Guidance

| Priority | OQ | Decide by | Why |
|---|---|---|---|
| 1 | OQ1 | Before enabling search-dependent Mission policies in deployment | Architecture is complete, but search cannot ship without current verifiable receipts. |

## Blocked Fact-Gate Targets

| OQ | Source owner / target | Exact fact to confirm | Why unavailable now |
|---|---|---|---|
| OQ1 | Current relay owner | Version/timeline that cleanly terminates root `/responses` over HTTP/1.1 and HTTP/2 while preserving search receipts | Provider transport implementation and roadmap are not represented in the repo. |

## Sources

- [`mission-runtime-overview.md`](mission-runtime-overview.md)
- `backend/src/services/search/model_native.py`
- `backend/src/mission_runtime/production.py`
- `backend/src/database/models/model_catalog.py`
- [OpenAI Web search guide](https://developers.openai.com/api/docs/guides/tools-web-search)
- Redacted live endpoint contract probes performed 2026-07-10; no API key or secret response payload is stored in this document.
