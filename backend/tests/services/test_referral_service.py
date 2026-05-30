"""Tests for ReferralService — focus on validation logic."""

import asyncio


def test_referral_service_import():
    """Verify the service module imports cleanly."""
    from src.services.referral_service import ReferralService
    assert ReferralService is not None


def test_referral_cannot_refer_self():
    """record() should reject referrer == referee."""
    async def _run():
        from src.services.referral_service import ReferralService
        svc = ReferralService()
        try:
            await svc.record(referrer_user_id="abc", referee_user_id="abc")
            return False
        except ValueError as e:
            return "cannot refer self" in str(e)

    result = asyncio.run(_run())
    assert result
