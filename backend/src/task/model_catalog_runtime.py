"""Worker/task helpers for the DataService-backed model catalog runtime cache."""

from __future__ import annotations

from logging import Logger
from typing import Any

from src.services.model_catalog_cache import (
    ModelCatalogSnapshot,
    refresh_model_catalog_cache,
)


async def refresh_runtime_model_catalog(
    dataservice: Any,
    *,
    logger: Logger | None = None,
    context: str = "model catalog runtime",
) -> ModelCatalogSnapshot:
    """Refresh process-local runtime model config before LLM work starts."""
    snapshot = await refresh_model_catalog_cache(dataservice)
    if logger is not None:
        logger.info(
            "%s cache loaded (%d models, version=%s)",
            context,
            len(snapshot.by_id),
            snapshot.version,
        )
    return snapshot
