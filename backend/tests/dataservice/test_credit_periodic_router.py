"""Route-level transaction tests for periodic credit grant pages."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.dataservice_app.routers import credit as credit_router
from src.dataservice_client.contracts.credit import CreditPeriodicGrantPageRequest


@pytest.mark.asyncio
async def test_periodic_grant_route_commits_exactly_one_page_uow() -> None:
    page = {
        "rules_evaluated": 1,
        "rules_fired": 1,
        "users_scanned": 2,
        "users_granted": 2,
        "next_cursor": "next-page",
    }
    domain = SimpleNamespace(
        process_periodic_grant_page=AsyncMock(return_value=page)
    )
    session = MagicMock()
    uow = SimpleNamespace(required_session=session, commit=AsyncMock())
    request = CreditPeriodicGrantPageRequest(batch_size=2)

    with patch.object(
        credit_router,
        "CreditDataService",
        return_value=domain,
    ) as service_factory:
        response = await credit_router.process_periodic_grant_page(request, uow)

    service_factory.assert_called_once_with(session, autocommit=False)
    domain.process_periodic_grant_page.assert_awaited_once_with(
        cursor=None,
        batch_size=2,
    )
    uow.commit.assert_awaited_once_with()
    assert response["data"] == page
