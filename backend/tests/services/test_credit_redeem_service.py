"""Tests for CreditRedeemService — focus on validation logic."""

import pytest

from src.services.credit_redeem_service import CreditRedeemService, RedeemError


# ============ Validation tests (sync, no DB needed) ============


def test_batch_generate_rejects_zero_amount():
    """batch_generate should reject amount <= 0."""
    import asyncio
    async def _run():
        from unittest.mock import AsyncMock
        db = AsyncMock()
        svc = CreditRedeemService(db)
        try:
            await svc.batch_generate(
                amount=0, count=10, max_uses=1, per_user_limit=1,
                expires_at=None, description="t", admin_id="admin",
            )
            return False
        except ValueError as e:
            return "amount must be > 0" in str(e)

    result = asyncio.get_event_loop().run_until_complete(_run())
    assert result


def test_batch_generate_rejects_negative_amount():
    import asyncio
    async def _run():
        from unittest.mock import AsyncMock
        db = AsyncMock()
        svc = CreditRedeemService(db)
        try:
            await svc.batch_generate(
                amount=-5, count=10, max_uses=1, per_user_limit=1,
                expires_at=None, description="t", admin_id="admin",
            )
            return False
        except ValueError as e:
            return "amount must be > 0" in str(e)

    result = asyncio.get_event_loop().run_until_complete(_run())
    assert result


def test_batch_generate_rejects_zero_count():
    import asyncio
    async def _run():
        from unittest.mock import AsyncMock
        db = AsyncMock()
        svc = CreditRedeemService(db)
        try:
            await svc.batch_generate(
                amount=100, count=0, max_uses=1, per_user_limit=1,
                expires_at=None, description="t", admin_id="admin",
            )
            return False
        except ValueError as e:
            return "count must be 1..10000" in str(e)

    result = asyncio.get_event_loop().run_until_complete(_run())
    assert result


def test_batch_generate_rejects_over_10000_count():
    import asyncio
    async def _run():
        from unittest.mock import AsyncMock
        db = AsyncMock()
        svc = CreditRedeemService(db)
        try:
            await svc.batch_generate(
                amount=100, count=10001, max_uses=1, per_user_limit=1,
                expires_at=None, description="t", admin_id="admin",
            )
            return False
        except ValueError as e:
            return "count must be 1..10000" in str(e)

    result = asyncio.get_event_loop().run_until_complete(_run())
    assert result


def test_batch_generate_rejects_zero_max_uses():
    import asyncio
    async def _run():
        from unittest.mock import AsyncMock
        db = AsyncMock()
        svc = CreditRedeemService(db)
        try:
            await svc.batch_generate(
                amount=100, count=10, max_uses=0, per_user_limit=1,
                expires_at=None, description="t", admin_id="admin",
            )
            return False
        except ValueError as e:
            return "max_uses and per_user_limit must be > 0" in str(e)

    result = asyncio.get_event_loop().run_until_complete(_run())
    assert result


def test_redeem_error_is_exception():
    err = RedeemError("test error")
    assert isinstance(err, Exception)
    assert str(err) == "test error"
