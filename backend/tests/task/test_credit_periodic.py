from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.dataservice_client.contracts.credit import CreditPeriodicGrantPagePayload
from src.task.tasks import credit_periodic


class _FakePeriodicPageClient:
    def __init__(
        self,
        responses: list[CreditPeriodicGrantPagePayload | Exception],
    ) -> None:
        self.responses = list(responses)
        self.commands = []

    async def process_credit_periodic_grant_page(self, command):  # noqa: ANN001, ANN201
        self.commands.append(command)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


@asynccontextmanager
async def _page_client_context(client: _FakePeriodicPageClient):
    yield client


@pytest.mark.asyncio
async def test_periodic_rules_skip_when_lock_is_held() -> None:
    fake_lock = SimpleNamespace(
        acquire=AsyncMock(return_value=False),
        owned=AsyncMock(return_value=False),
        release=AsyncMock(),
    )
    fake_redis = SimpleNamespace(
        is_connected=True,
        client=SimpleNamespace(lock=Mock(return_value=fake_lock)),
        connect=AsyncMock(),
        disconnect=AsyncMock(),
    )

    with (
        patch.object(credit_periodic, "RedisClient", return_value=fake_redis),
        patch.object(
            credit_periodic,
            "_process_periodic_rules_inner",
            AsyncMock(),
        ) as inner,
    ):
        result = await credit_periodic._process_periodic_rules()

    assert result == {"rules_evaluated": 0, "rules_fired": 0, "users_granted": 0}
    fake_lock.acquire.assert_awaited_once_with(blocking=False)
    inner.assert_not_awaited()
    fake_lock.release.assert_not_awaited()
    fake_redis.disconnect.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_periodic_rules_release_lock_after_run() -> None:
    fake_lock = SimpleNamespace(
        acquire=AsyncMock(return_value=True),
        owned=AsyncMock(return_value=True),
        release=AsyncMock(),
    )
    fake_redis = SimpleNamespace(
        is_connected=True,
        client=SimpleNamespace(lock=Mock(return_value=fake_lock)),
        connect=AsyncMock(),
        disconnect=AsyncMock(),
    )
    summary = {"rules_evaluated": 1, "rules_fired": 1, "users_granted": 3}

    with (
        patch.object(credit_periodic, "RedisClient", return_value=fake_redis),
        patch.object(
            credit_periodic,
            "_process_periodic_rules_inner",
            AsyncMock(return_value=summary),
        ) as inner,
    ):
        result = await credit_periodic._process_periodic_rules()

    assert result == summary
    fake_lock.acquire.assert_awaited_once_with(blocking=False)
    inner.assert_awaited_once_with()
    fake_lock.owned.assert_awaited_once_with()
    fake_lock.release.assert_awaited_once_with()
    fake_redis.disconnect.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_periodic_task_drives_all_dataservice_pages_and_aggregates() -> None:
    client = _FakePeriodicPageClient(
        [
            CreditPeriodicGrantPagePayload(
                rules_evaluated=1,
                rules_fired=1,
                users_scanned=100,
                users_granted=100,
                next_cursor="cursor-1",
            ),
            CreditPeriodicGrantPagePayload(
                rules_evaluated=0,
                rules_fired=0,
                users_scanned=100,
                users_granted=98,
                next_cursor="cursor-2",
            ),
            CreditPeriodicGrantPagePayload(
                rules_evaluated=1,
                rules_fired=1,
                users_scanned=7,
                users_granted=7,
                next_cursor=None,
            ),
        ]
    )

    with patch.object(
        credit_periodic,
        "dataservice_client",
        return_value=_page_client_context(client),
    ):
        summary = await credit_periodic._process_periodic_rules_inner()

    assert summary == {
        "rules_evaluated": 2,
        "rules_fired": 2,
        "users_granted": 205,
    }
    assert [command.cursor for command in client.commands] == [
        None,
        "cursor-1",
        "cursor-2",
    ]
    assert all(
        command.batch_size == credit_periodic._BATCH_SIZE
        for command in client.commands
    )


@pytest.mark.asyncio
async def test_periodic_task_failure_recovers_by_restarting_from_ledger() -> None:
    failed_client = _FakePeriodicPageClient(
        [
            CreditPeriodicGrantPagePayload(
                rules_evaluated=1,
                rules_fired=1,
                users_scanned=2,
                users_granted=2,
                next_cursor="cursor-1",
            ),
            RuntimeError("dataservice unavailable"),
        ]
    )
    with (
        patch.object(
            credit_periodic,
            "dataservice_client",
            return_value=_page_client_context(failed_client),
        ),
        pytest.raises(RuntimeError, match="dataservice unavailable"),
    ):
        await credit_periodic._process_periodic_rules_inner()

    recovered_client = _FakePeriodicPageClient(
        [
            CreditPeriodicGrantPagePayload(
                rules_evaluated=1,
                rules_fired=1,
                users_scanned=2,
                users_granted=0,
                next_cursor="cursor-1",
            ),
            CreditPeriodicGrantPagePayload(
                rules_evaluated=0,
                rules_fired=0,
                users_scanned=3,
                users_granted=3,
                next_cursor=None,
            ),
        ]
    )
    with patch.object(
        credit_periodic,
        "dataservice_client",
        return_value=_page_client_context(recovered_client),
    ):
        summary = await credit_periodic._process_periodic_rules_inner()

    assert failed_client.commands[0].cursor is None
    assert recovered_client.commands[0].cursor is None
    assert summary["users_granted"] == 3


def test_periodic_task_retries_after_worker_or_transport_failure() -> None:
    task = credit_periodic.process_credit_grant_rules

    assert task.acks_late is True
    assert task.reject_on_worker_lost is True
    assert task.autoretry_for == (Exception,)
    assert task.retry_backoff is True
    assert task.retry_jitter is True
    assert task.max_retries == 5
