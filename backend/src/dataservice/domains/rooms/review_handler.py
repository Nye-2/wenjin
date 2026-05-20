"""Review handlers for workspace room materialization."""

from __future__ import annotations

from typing import Any

from src.dataservice.domains.rooms.service import RoomsDataDomainService


def build_room_review_handler(service: RoomsDataDomainService):
    """Build a review handler that materializes accepted room write payloads."""

    async def handler(item: Any) -> dict[str, Any]:
        return await service.apply_review_item(item)

    return handler
