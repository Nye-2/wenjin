"""Receipt-backed search tool surface."""

from src.services.search.model_native import (
    MODEL_NATIVE_SEARCH_TOOL_ID,
    ModelNativeSearchInput,
    NativeSearchCapability,
    NativeSearchReceipt,
    build_native_search_payload,
    model_native_search_registration,
    native_search_capability,
    parse_native_search_receipt,
)
from src.services.search.responses_sse import (
    ResponsesSearchSSEParser,
    ResponsesSearchSSEProtocolError,
)

__all__ = [
    "MODEL_NATIVE_SEARCH_TOOL_ID",
    "ModelNativeSearchInput",
    "NativeSearchCapability",
    "NativeSearchReceipt",
    "ResponsesSearchSSEParser",
    "ResponsesSearchSSEProtocolError",
    "build_native_search_payload",
    "model_native_search_registration",
    "native_search_capability",
    "parse_native_search_receipt",
]
