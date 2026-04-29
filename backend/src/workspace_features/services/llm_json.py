"""Shared helpers for bounded JSON-only LLM generation in workspace features."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Sequence
from typing import Any, Literal

from src.models.factory import create_chat_model
from src.models.router import list_user_selectable_models, route_writing_model
from src.services.token_usage_collector import record_token_usage

JsonValue = dict[str, Any] | list[Any]

_JSON_SYSTEM_RULES = "\n".join(
    [
        "你在问津 Compute feature 执行链路中工作，必须基于当前工作区上下文生成可落库产物。",
        "你必须只返回一个 JSON 值（对象或数组，以 schema 为准）。",
        "不要输出 Markdown 代码块、解释性前缀或额外结语。",
        "字段名必须与给定 schema 完全一致。",
        "JSON 必须语法有效：使用双引号，不要尾随逗号，不要把注释写进 JSON。",
        "先在内部完成分析，再直接输出最终 JSON。",
        "优先给出可直接执行、可直接落稿的内容，避免空泛套话。",
        "只使用提供的上下文和工作区产物；不要编造具体论文、专利号、期刊指标、实验结果、引用或法规事实。",
        "把已知事实、基于事实的推断和待核验内容区分清楚；关键信息不足时给出保守占位并明确标注待补充/待核验。",
        "不得向用户提问；缺失信息必须写入 JSON 字段中的待补充项或建议动作。",
    ]
)
_DEFAULT_SECTION_CHAR_LIMIT = 2400
_DEFAULT_TOTAL_CHAR_LIMIT = 12000


def extract_response_text(response: Any) -> str:
    """Extract plain text from a chat-model response object."""
    content = getattr(response, "content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        texts: list[str] = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                texts.append(item["text"])
        return "\n".join(texts).strip()
    return str(content).strip()


def parse_json_value(raw_text: str) -> JsonValue | None:
    """Parse a JSON object or array from a model response with fence/body fallbacks."""
    if not raw_text:
        return None

    candidates = [raw_text.strip()]
    code_block_match = re.search(
        r"```json\s*(.*?)\s*```",
        raw_text,
        re.DOTALL | re.IGNORECASE,
    )
    if code_block_match:
        candidates.append(code_block_match.group(1).strip())

    first_brace = raw_text.find("{")
    last_brace = raw_text.rfind("}")
    if first_brace != -1 and last_brace != -1 and first_brace < last_brace:
        candidates.append(raw_text[first_brace : last_brace + 1].strip())

    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, (dict, list)):
            return payload
    return None


def parse_json_payload(raw_text: str) -> dict[str, Any] | None:
    """Parse a JSON object from a model response with fence/body fallbacks."""
    payload = parse_json_value(raw_text)
    return payload if isinstance(payload, dict) else None


def parse_json_array(raw_text: str) -> list[dict[str, Any]] | None:
    """Parse a JSON array of objects from a model response with fence/body fallbacks."""
    payload = parse_json_value(raw_text)
    if isinstance(payload, list) and all(isinstance(item, dict) for item in payload):
        return payload
    return None


def _render_prompt_value(value: str | Iterable[str] | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    parts = [str(item).strip() for item in value if str(item).strip()]
    return "\n".join(parts) if parts else None


def _truncate_text(value: str, *, limit: int) -> str:
    if len(value) <= limit:
        return value
    suffix = "\n...[truncated]"
    budget = max(0, limit - len(suffix))
    return value[:budget].rstrip() + suffix


def resolve_writing_model_id(preferred_model: str | None) -> str | None:
    """Resolve the writing model id or return ``None`` if none are configured."""
    models = list_user_selectable_models(purpose="writing")
    if not models:
        return None
    try:
        return route_writing_model(requested_model=preferred_model)
    except Exception:
        return models[0].id


def build_json_prompt(
    *,
    instruction: str,
    context_sections: Sequence[tuple[str, str | Iterable[str] | None]],
    schema: str,
    requirements: Sequence[str] = (),
    output_language: str | None = None,
    max_section_chars: int = _DEFAULT_SECTION_CHAR_LIMIT,
    max_total_chars: int = _DEFAULT_TOTAL_CHAR_LIMIT,
) -> str:
    """Build a consistent JSON-generation prompt with bounded sections."""
    lines: list[str] = [instruction.strip()]

    if output_language:
        lines.append(f"输出自然语言字段：{output_language}")

    for title, body in context_sections:
        rendered = _render_prompt_value(body)
        if not rendered:
            continue
        rendered = _truncate_text(rendered, limit=max_section_chars)
        lines.extend(["", f"{title}：", rendered])

    lines.extend(
        [
            "",
            "JSON Schema:",
            schema,
        ]
    )

    if requirements:
        lines.append("")
        lines.append("要求：")
        lines.extend(f"{index}. {item}" for index, item in enumerate(requirements, start=1))

    lines.extend(
        [
            "",
            "硬性约束：",
            "1. 只返回 JSON，不要输出 Markdown 代码块或额外说明。",
            "2. 严格遵守 schema 的字段名和层级；缺失列表返回空数组，缺失对象返回空对象，不要返回 null。",
            "3. 不要编造未提供的论文、专利号、期刊指标、实验结果、统计指标、引用或法规事实。",
            "4. 如果缺关键事实，请在字段值中明确标注“待补充/待核验”，并给出下一步补证动作。",
            "5. 优先复用上下文中的工作区产物，不要重启需求发现或向用户提问。",
            "6. 先保证 JSON 结构正确，再保证语言凝练、信息密度高、可直接使用。",
        ]
    )
    return _truncate_text("\n".join(lines), limit=max_total_chars)


def build_json_system_prompt(role_prompt: str) -> str:
    """Compose a stable system prompt for JSON-only generation."""
    normalized = role_prompt.strip()
    if not normalized:
        return _JSON_SYSTEM_RULES
    return f"{normalized}\n\n{_JSON_SYSTEM_RULES}"


async def invoke_json_chat_model(
    *,
    system_prompt: str,
    prompt: str,
    preferred_model: str | None = None,
    resolved_model_id: str | None = None,
    temperature: float = 0.2,
    expected_type: Literal["object", "array"] = "object",
) -> tuple[JsonValue | None, str | None, str | None]:
    """Run the selected writing model and parse a JSON object from its output."""
    model_id = str(resolved_model_id).strip() if resolved_model_id else resolve_writing_model_id(preferred_model)
    if model_id is None:
        return None, None, "no_generation_model_configured"

    try:
        from langchain_core.messages import HumanMessage, SystemMessage
    except Exception as exc:
        return None, model_id, f"langchain_message_import_failed: {exc}"

    try:
        model = create_chat_model(model_id, temperature=temperature)
    except Exception as exc:
        return None, model_id, f"model_init_failed: {exc}"

    try:
        response = await model.ainvoke(
            [
                SystemMessage(content=build_json_system_prompt(system_prompt)),
                HumanMessage(content=prompt),
            ]
        )
        record_token_usage(response)
    except Exception as exc:
        return None, model_id, f"llm_generation_failed: {exc}"

    raw_text = extract_response_text(response)
    if expected_type == "array":
        parsed = parse_json_array(raw_text)
    else:
        parsed = parse_json_payload(raw_text)
    if parsed is None:
        return None, model_id, f"llm_output_not_json_{expected_type}"
    return parsed, model_id, None
