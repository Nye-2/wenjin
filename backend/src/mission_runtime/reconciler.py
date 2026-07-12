"""Recover dropped Mission wakeups from DataService runnable truth."""

from __future__ import annotations

import logging

from src.dataservice_client.contracts.mission import (
    MissionDispatchReleasePayload,
    MissionRunnableBatchClaimPayload,
)
from src.dataservice_client.errors import DataServiceClientError
from src.mission_runtime.ports import (
    MissionClockPort,
    MissionEventPublisherPort,
    MissionStorePort,
    MissionWakeupPublisherPort,
    SystemMissionClock,
)

logger = logging.getLogger(__name__)


class MissionReconciler:
    """Fence dispatch without consuming due state, then publish wakeup hints."""

    def __init__(
        self,
        *,
        store: MissionStorePort,
        wakeups: MissionWakeupPublisherPort,
        events: MissionEventPublisherPort,
        clock: MissionClockPort | None = None,
        lease_ttl_seconds: int = 60,
    ) -> None:
        self.store = store
        self.wakeups = wakeups
        self.events = events
        self.clock = clock or SystemMissionClock()
        self.lease_ttl_seconds = lease_ttl_seconds

    async def reconcile_once(
        self,
        *,
        worker_id: str,
        limit: int = 20,
    ) -> list[str]:
        claimed = await self.store.claim_runnable(
            MissionRunnableBatchClaimPayload(
                worker_id=worker_id,
                ttl_seconds=self.lease_ttl_seconds,
                limit=limit,
            )
        )
        published: list[str] = []
        for run in claimed:
            try:
                await self.wakeups.publish(run.mission_id)
            except Exception:
                logger.warning(
                    "Reconciler wakeup publish failed for %s; due row remains recoverable",
                    run.mission_id,
                    exc_info=True,
                )
                try:
                    await self.store.release_dispatch(
                        run.mission_id,
                        MissionDispatchReleasePayload(
                            worker_id=worker_id,
                            dispatch_epoch=run.dispatch_epoch,
                        ),
                    )
                except DataServiceClientError as exc:
                    if exc.status_code != 409:
                        raise
                continue
            published.append(run.mission_id)
        return published


__all__ = ["MissionReconciler"]
