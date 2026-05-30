"""Dashboard-domain dependency factories."""

from fastapi import Depends

from src.dataservice_client import AsyncDataServiceClient
from src.gateway.deps.core import get_dataservice_client
from src.services.admin_dashboard_service import AdminDashboardService
from src.services.credit_service import CreditService
from src.services.dashboard_service import DashboardService
from src.services.release_gate_service import ReleaseGateService
from src.services.user_dashboard_service import UserDashboardService
from src.services.workspace_activity_service import WorkspaceActivityService
from src.services.workspace_summary_service import WorkspaceSummaryService


async def get_dashboard_service(
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> DashboardService:
    """Get dashboard service instance."""
    return DashboardService(dataservice=dataservice)


async def get_credit_service(
) -> CreditService:
    """Get credit service instance."""
    return CreditService()


async def get_user_dashboard_service(
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> UserDashboardService:
    """Get user dashboard service instance."""
    return UserDashboardService(dataservice=dataservice)


async def get_admin_dashboard_service(
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> AdminDashboardService:
    """Get admin dashboard service instance."""
    return AdminDashboardService(dataservice=dataservice)


async def get_release_gate_service() -> ReleaseGateService:
    """Get release gate service instance."""
    return ReleaseGateService()


async def get_workspace_activity_service(
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> WorkspaceActivityService:
    """Get workspace activity service instance."""
    return WorkspaceActivityService(dataservice=dataservice)


async def get_workspace_summary_service(
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> WorkspaceSummaryService:
    """Get workspace summary service instance."""
    return WorkspaceSummaryService(dataservice=dataservice)
