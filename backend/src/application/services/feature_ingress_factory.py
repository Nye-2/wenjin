"""Factory helpers for the canonical feature ingress service."""

from __future__ import annotations

from typing import Any

from src.academic.services.workspace_service import WorkspaceService
from src.application.services.feature_submission_service import FeatureSubmissionService
from src.compute.session_service import ComputeSessionService
from src.services.credit_service import CreditService
from src.services.execution_service import ExecutionService
from src.services.references import WorkspaceReferenceService

from .feature_launch_service import FeatureIngressService


def build_feature_ingress_service(
    *,
    actor_id: str,
    db: Any,
    workspace_service: WorkspaceService,
    reference_service: WorkspaceReferenceService,
    credit_service: CreditService,
) -> FeatureIngressService:
    """Build the single application-level feature launch/resume entrypoint."""
    feature_submission_service = FeatureSubmissionService(
        actor_id=str(actor_id),
        workspace_service=workspace_service,
        reference_service=reference_service,
        credit_service=credit_service,
        execution_service=ExecutionService(db),
    )
    return FeatureIngressService(
        actor_id=str(actor_id),
        feature_submission_service=feature_submission_service,
        execution_service=ExecutionService(db),
        compute_session_service=ComputeSessionService(db),
        workspace_service=workspace_service,
    )
