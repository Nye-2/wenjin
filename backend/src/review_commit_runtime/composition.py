"""Production composition for the unique Mission review/preview graph."""

from __future__ import annotations

from functools import lru_cache

from src.config.app_config import get_settings
from src.dataservice_client import AsyncDataServiceClient

from .materializer import MissionDomainWriter
from .membership import DataServiceMembershipAuthorizer
from .preview_store import MissionPreviewStore
from .runtime import ReviewCommitRuntime


@lru_cache(maxsize=1)
def get_mission_preview_store() -> MissionPreviewStore:
    settings = get_settings()
    return MissionPreviewStore(
        settings.mission_preview_root,
        default_ttl_seconds=settings.mission_preview_ttl_seconds,
        max_bytes=settings.mission_preview_max_bytes,
    )


def build_review_commit_runtime(dataservice: AsyncDataServiceClient) -> ReviewCommitRuntime:
    settings = get_settings()
    previews = get_mission_preview_store()
    return ReviewCommitRuntime(
        missions=dataservice.missions,
        target_writer=MissionDomainWriter(
            dataservice,
            preview_store=previews,
            workspace_asset_root=settings.workspace_asset_root,
        ),
        membership=DataServiceMembershipAuthorizer(dataservice),
        preview_store=previews,
    )


__all__ = ["build_review_commit_runtime", "get_mission_preview_store"]
