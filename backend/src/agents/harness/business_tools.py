"""Bounded business-context tools for ReactSubagent team members."""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from src.sandbox.workspace_layout import (
    is_workspace_internal_path,
    is_workspace_protected_path,
)
from src.subagents.v2.base import SubagentContext

BUSINESS_TOOL_NAMES = frozenset(
    {
        "library_read",
        "document_read",
        "memory_read",
        "prism_read",
        "citation_parser",
        "artifact_create",
    }
)

_MAX_TEXT_CHARS = 4000
_DEFAULT_LIMIT = 10
_MAX_LIMIT = 50


class LibraryReadInput(BaseModel):
    query: str | None = None
    limit: int = Field(default=20, ge=1, le=50)


class DocumentReadInput(BaseModel):
    query: str | None = None
    limit: int = Field(default=10, ge=1, le=30)


class MemoryReadInput(BaseModel):
    query: str | None = None
    limit: int = Field(default=10, ge=1, le=30)


class PrismReadInput(BaseModel):
    section: str | None = None


class CitationParserInput(BaseModel):
    text: str


class ArtifactCreateInput(BaseModel):
    title: str
    markdown: str
    kind: str = "review_report"


BusinessHandler = Callable[[SubagentContext, dict[str, Any]], Awaitable[str]]


def build_business_langchain_tools(ctx: SubagentContext, tool_names: list[str]) -> list[StructuredTool]:
    """Build LangChain tools for workspace business context.

    These tools only read the bounded `SubagentContext.workspace_data` snapshot
    or return staged payloads. They do not commit rooms or mutate Prism files.
    """

    tools: list[StructuredTool] = []
    for name in _dedupe_tool_names(tool_names):
        definition = BUSINESS_TOOL_DEFINITIONS.get(name)
        if definition is None:
            continue
        description, args_schema, handler = definition
        tools.append(
            StructuredTool.from_function(
                coroutine=_business_coroutine(ctx, handler),
                name=name,
                description=description,
                args_schema=args_schema,
            )
        )
    return tools


def _business_coroutine(ctx: SubagentContext, handler: BusinessHandler):
    async def _coroutine(**kwargs) -> str:
        args_summary = _summarize_args(kwargs)
        records = ctx.workspace_data.get("_harness_tool_records")
        try:
            result = await handler(ctx, kwargs)
        except Exception as exc:
            if isinstance(records, list):
                records.append(
                    {
                        "name": _handler_name(handler),
                        "status": "failed",
                        "args": args_summary,
                        "error": f"{exc.__class__.__name__}: {str(exc)[:500]}",
                    }
                )
            raise
        if isinstance(records, list):
            records.append(
                {
                    "name": _handler_name(handler),
                    "status": "completed",
                    "args": args_summary,
                    "result_preview": result[:500],
                }
            )
        return result

    return _coroutine


async def _library_read(ctx: SubagentContext, args: dict[str, Any]) -> str:
    items = _extract_collection(ctx.workspace_data.get("library"), "items")
    matched = _filter_items(items, args.get("query"), int(args.get("limit") or 20))
    return _format_business_result(
        "library_read",
        "Library sources returned.",
        {"items": matched, "total": len(items), "returned": len(matched)},
        truncated=len(matched) < len(_filter_items(items, args.get("query"), _MAX_LIMIT)),
    )


async def _document_read(ctx: SubagentContext, args: dict[str, Any]) -> str:
    items = _extract_collection(ctx.workspace_data.get("documents"), "items")
    matched = _filter_items(items, args.get("query"), int(args.get("limit") or _DEFAULT_LIMIT))
    return _format_business_result(
        "document_read",
        "Document excerpts returned.",
        {"items": matched, "total": len(items), "returned": len(matched)},
        truncated=len(matched) < len(_filter_items(items, args.get("query"), _MAX_LIMIT)),
    )


async def _memory_read(ctx: SubagentContext, args: dict[str, Any]) -> str:
    items = _extract_collection(ctx.workspace_data.get("memory"), "items")
    matched = _filter_items(items, args.get("query"), int(args.get("limit") or _DEFAULT_LIMIT))
    return _format_business_result(
        "memory_read",
        "Workspace memory facts returned.",
        {"items": matched, "total": len(items), "returned": len(matched)},
        truncated=len(matched) < len(_filter_items(items, args.get("query"), _MAX_LIMIT)),
    )


async def _prism_read(ctx: SubagentContext, args: dict[str, Any]) -> str:
    prism = ctx.workspace_data.get("prism")
    payload = _sanitize_public_value(prism if isinstance(prism, dict) else {})
    if not isinstance(payload, dict):
        payload = {}
    payload.pop("full_text", None)
    payload.pop("content", None)
    section = str(args.get("section") or "").strip().lower()
    if section and isinstance(payload.get("outline"), list):
        payload["outline"] = [
            item for item in payload["outline"]
            if section in str(item).lower()
        ]
    return _format_business_result("prism_read", "Prism lightweight context returned.", payload)


async def _citation_parser(ctx: SubagentContext, args: dict[str, Any]) -> str:
    _ = ctx
    text = str(args.get("text") or "")
    citation_keys = sorted(
        {
            key.strip()
            for group in re.findall(r"\\cite[tp]?\{([^}]+)\}", text)
            for key in group.split(",")
            if key.strip()
        }
        | {key for key in re.findall(r"@([A-Za-z0-9_:.-]+)", text)}
    )
    dois = sorted(set(re.findall(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+\b", text)))
    urls = sorted(set(re.findall(r"https?://[^\s)>\"]+", text)))
    return _format_business_result(
        "citation_parser",
        "Citation-like tokens parsed.",
        {
            "citation_keys": citation_keys[:50],
            "dois": dois[:50],
            "urls": urls[:50],
        },
    )


async def _artifact_create(ctx: SubagentContext, args: dict[str, Any]) -> str:
    _ = ctx
    title = _compact_text(args.get("title"))
    markdown = _compact_text(args.get("markdown"))
    kind = _safe_kind(args.get("kind"))
    return _format_business_result(
        "artifact_create",
        "Artifact staged for review.",
        {
            "staged_artifact": {
                "title": title,
                "kind": kind,
                "markdown_preview": markdown,
                "status": "staged_for_review",
                "materialized": False,
            }
        },
        truncated=len(str(args.get("markdown") or "")) > len(markdown),
    )


BUSINESS_TOOL_DEFINITIONS: dict[str, tuple[str, type[BaseModel], BusinessHandler]] = {
    "library_read": ("Read bounded Workspace Library source summaries.", LibraryReadInput, _library_read),
    "document_read": ("Read bounded workspace document excerpts.", DocumentReadInput, _document_read),
    "memory_read": ("Read bounded workspace memory facts.", MemoryReadInput, _memory_read),
    "prism_read": ("Read lightweight Prism manuscript context.", PrismReadInput, _prism_read),
    "citation_parser": ("Parse citation keys, DOI-like tokens, and URLs from text.", CitationParserInput, _citation_parser),
    "artifact_create": ("Stage a reviewable artifact payload without committing rooms.", ArtifactCreateInput, _artifact_create),
}


def _extract_collection(value: Any, key: str) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        raw = value.get(key) or value.get("records") or value.get("sources") or []
    else:
        raw = value
    if not isinstance(raw, list):
        return []
    result: list[dict[str, Any]] = []
    for item in raw:
        sanitized = _sanitize_public_value(item)
        if isinstance(sanitized, dict) and sanitized:
            result.append(sanitized)
    return result


def _filter_items(items: list[dict[str, Any]], query: Any, limit: int) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit or _DEFAULT_LIMIT), _MAX_LIMIT))
    query_terms = [term.lower() for term in re.findall(r"\w+", str(query or "")) if term.strip()]
    matched: list[dict[str, Any]] = []
    for item in items:
        haystack = json.dumps(item, ensure_ascii=False).lower()
        if query_terms and not all(term in haystack for term in query_terms):
            continue
        matched.append(item)
        if len(matched) >= limit:
            break
    return matched


def _sanitize_public_value(value: Any) -> Any:
    if isinstance(value, dict):
        if _dict_has_blocked_ref(value):
            return None
        result: dict[str, Any] = {}
        for key, item in value.items():
            sanitized = _sanitize_public_value(item)
            if sanitized is not None:
                result[str(key)] = sanitized
        return result
    if isinstance(value, list | tuple):
        result = []
        for item in value[:_MAX_LIMIT]:
            sanitized = _sanitize_public_value(item)
            if sanitized is not None:
                result.append(sanitized)
        return result
    if isinstance(value, str):
        if _blocked_workspace_ref(value):
            return None
        return _compact_text(value)
    return value


def _blocked_workspace_ref(value: str) -> bool:
    text = str(value or "").strip()
    if not text.startswith("/workspace"):
        return False
    return is_workspace_internal_path(text) or is_workspace_protected_path(text)


def _dict_has_blocked_ref(value: dict[str, Any]) -> bool:
    for item in value.values():
        if isinstance(item, str) and _blocked_workspace_ref(item):
            return True
    return False


def _format_business_result(
    tool: str,
    preview: str,
    payload: dict[str, Any],
    *,
    truncated: bool = False,
) -> str:
    return json.dumps(
        {
            "preview": preview,
            "payload": {
                "schema": "wenjin.harness.business_tool_result.v1",
                "tool": tool,
                **payload,
            },
            "truncated": truncated,
            "externalized": False,
            "output_refs": [],
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _safe_kind(value: Any) -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "review_report")).strip("_")
    return text or "review_report"


def _compact_text(value: Any) -> str:
    text = str(value or "").strip()
    return text if len(text) <= _MAX_TEXT_CHARS else f"{text[: _MAX_TEXT_CHARS - 3]}..."


def _dedupe_tool_names(tool_names: list[str]) -> list[str]:
    result: list[str] = []
    for name in tool_names:
        text = str(name or "").strip()
        if text in BUSINESS_TOOL_NAMES and text not in result:
            result.append(text)
    return result


def _handler_name(handler: BusinessHandler) -> str:
    name = getattr(handler, "__name__", "")
    return str(name).removeprefix("_")


def _summarize_args(args: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for key, value in args.items():
        if isinstance(value, str) and len(value) > 500:
            summary[key] = f"{value[:500]}... ({len(value)} chars)"
        else:
            summary[key] = value
    return summary
