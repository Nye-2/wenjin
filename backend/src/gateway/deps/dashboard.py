"""Dashboard-domain dependency factories."""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.gateway.deps.core import get_db
from src.services.admin_dashboard_service import AdminDashboardService
from src.services.credit_service import CreditService
from src.services.dashboard_service import DashboardService
from src.services.release_gate_service import ReleaseGateService
from src.services.user_dashboard_service import UserDashboardService
from src.services.workspace_activity_service import WorkspaceActivityService


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
) -> UserDashboardService:
    """Get user dashboard service instance."""
    return UserDashboardService(db)


async def get_admin_dashboard_service(
    db: AsyncSession = Depends(get_db),
) -> AdminDashboardService:
    """Get admin dashboard service instance."""
    return AdminDashboardService(db)


async def get_release_gate_service() -> ReleaseGateService:
    """Get release gate service instance."""
    return ReleaseGateService()


async def get_workspace_activity_service(
    db: AsyncSession = Depends(get_db),
) -> WorkspaceActivityService:
    """Get workspace activity service instance."""
    return WorkspaceActivityService(db)
