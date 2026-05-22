"""Dashboard-domain dependency factories."""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice_client import AsyncDataServiceClient
from src.gateway.deps.core import get_dataservice_client, get_db
from src.services.admin_dashboard_service import AdminDashboardService
from src.services.credit_service import CreditService
from src.services.dashboard_service import DashboardService
from src.services.release_gate_service import ReleaseGateService
from src.services.user_dashboard_service import UserDashboardService
from src.services.workspace_activity_service import WorkspaceActivityService
from src.services.workspace_summary_service import WorkspaceSummaryService


async def get_dashboard_service(
    db: AsyncSession = Depends(get_db),
) -> DashboardService:
    """Get dashboard service instance."""
    return DashboardService(db)


async def get_credit_service(
    db: AsyncSession = Depends(get_db),
) -> CreditService:
    """Get credit service instance."""
    return CreditService(db)


async def get_user_dashboard_service(
    db: AsyncSession = Depends(get_db),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> UserDashboardService:
    """Get user dashboard service instance."""
    return UserDashboardService(db, dataservice=dataservice)


async def get_admin_dashboard_service(
    db: AsyncSession = Depends(get_db),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> AdminDashboardService:
    """Get admin dashboard service instance."""
    return AdminDashboardService(db, dataservice=dataservice)


async def get_release_gate_service() -> ReleaseGateService:
    """Get release gate service instance."""
    return ReleaseGateService()


async def get_workspace_activity_service(
    db: AsyncSession = Depends(get_db),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> WorkspaceActivityService:
    """Get workspace activity service instance."""
    return WorkspaceActivityService(db, dataservice=dataservice)


async def get_workspace_summary_service(
    db: AsyncSession = Depends(get_db),
) -> WorkspaceSummaryService:
    """Get workspace summary service instance."""
    return WorkspaceSummaryService(db)
