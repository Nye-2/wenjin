"""Tests for bounded periodic-credit DataService client contracts."""

from __future__ import annotations

import pytest

from src.dataservice_client.contracts.credit import CreditPeriodicGrantPageRequest
from src.dataservice_client.credit_client import CreditDataServiceClientMixin


class _CreditClient(CreditDataServiceClientMixin):
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict]] = []

    async def _request(
        self,
        method: str,
        path: str,
        *,
        authenticated: bool = True,
        **kwargs,
    ) -> dict:
        self.calls.append((method, path, kwargs))
        return {
            "data": {
                "rules_evaluated": 1,
                "rules_fired": 1,
                "users_scanned": 100,
                "users_granted": 99,
                "next_cursor": "next-page",
            }
        }


@pytest.mark.asyncio
async def test_periodic_grant_client_calls_single_page_endpoint() -> None:
    client = _CreditClient()
    command = CreditPeriodicGrantPageRequest(
        cursor="current-page",
        batch_size=25,
    )

    page = await client.process_credit_periodic_grant_page(command)

    assert client.calls == [
        (
            "POST",
            "/internal/v1/credit/periodic-grants/process-page",
            {
                "json": {
                    "cursor": "current-page",
                    "batch_size": 25,
                }
            },
        )
    ]
    assert page.users_granted == 99
    assert page.next_cursor == "next-page"
