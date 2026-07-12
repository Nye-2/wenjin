"""Transient mission projection events published strictly after persistence."""

from __future__ import annotations

import logging

from src.dataservice_client.contracts.mission import MissionRunPayload
from src.mission_runtime.contracts import (
    MissionEventEnvelope,
    MissionEventType,
)
from src.mission_runtime.ports import MissionClockPort, MissionEventPublisherPort

logger = logging.getLogger(__name__)


def event_type_for_run(run: MissionRunPayload, *, created: bool = False) -> MissionEventType:
    if created:
        return MissionEventType.CREATED
    mapping = {
        "waiting": MissionEventType.WAITING,
        "completed": MissionEventType.COMPLETED,
        "failed": MissionEventType.FAILED,
        "cancelled": MissionEventType.CANCELLED,
    }
    return mapping.get(run.status.value, MissionEventType.UPDATED)


async def publish_after_commit(
    publisher: MissionEventPublisherPort,
    clock: MissionClockPort,
    run: MissionRunPayload,
    *,
    created: bool = False,
) -> bool:
    """Publish an invalidation hint; committed mission facts never depend on it."""
    event_type = event_type_for_run(run, created=created)
    event = MissionEventEnvelope(
        event_id=f"{run.mission_id}:{run.state_version}:{run.last_item_seq}:{event_type.value}",
        event_type=event_type,
        mission_id=run.mission_id,
        workspace_id=run.workspace_id,
        status=run.status.value,
        state_version=run.state_version,
        last_item_seq=run.last_item_seq,
        occurred_at=clock.now(),
    )
    try:
        await publisher.publish(event)
    except Exception:
        logger.warning(
            "Transient MissionEvent publish failed for mission %s at version %s",
            run.mission_id,
            run.state_version,
            exc_info=True,
        )
        return False
    return True


__all__ = ["event_type_for_run", "publish_after_commit"]
