"""Structural tests verifying billing concurrency safety.

These tests ensure that ``CreditService.can_start_chat_turn`` acquires a
row-level lock (``SELECT ... FOR UPDATE``) on the user row when it needs to
check the credit balance.  Without the lock two concurrent requests could both
pass the budget gate before either deducts credits.
"""

from __future__ import annotations

import ast
import inspect
import textwrap
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.database.models.credit import CreditTransaction, CreditTransactionType
from src.database.models.user import User
from src.services.credit_service import CreditService

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


# ---------------------------------------------------------------------------
# Fixtures (mirrors test_credit_service.py)
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def async_engine():
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(User.__table__.create)
        await conn.run_sync(CreditTransaction.__table__.create)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(CreditTransaction.__table__.drop)
        await conn.run_sync(User.__table__.drop)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(async_engine):
    async_session_maker = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    async with async_session_maker() as session:
        yield session


@pytest_asyncio.fixture
async def credit_service(db_session):
    return CreditService(db_session)


async def _create_user(
    db_session: AsyncSession,
    *,
    user_id: str = "user-1",
    credits: int = 10,
) -> User:
    user = User(
        id=user_id,
        email=f"{user_id}@example.com",
        name=user_id,
        hashed_password="hashed",
        credits=credits,
        total_credits_earned=credits,
        total_credits_spent=0,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _create_chat_transaction(
    db_session: AsyncSession,
    *,
    user_id: str,
    amount: int,
    total_tokens: int,
    balance_after: int,
) -> CreditTransaction:
    tx = CreditTransaction(
        user_id=user_id,
        transaction_type=CreditTransactionType.CHAT_TOKEN_CONSUME,
        amount=amount,
        balance_after=balance_after,
        description="seed chat tx",
        feature_id="chat",
        tx_metadata={"token_usage": {"total_tokens": total_tokens}},
    )
    db_session.add(tx)
    await db_session.commit()
    await db_session.refresh(tx)
    return tx


# ---------------------------------------------------------------------------
# 1. Source-level structural test: can_start_chat_turn calls
#    _get_user_for_update (which issues SELECT … FOR UPDATE)
# ---------------------------------------------------------------------------

class TestCanStartChatTurnUsesRowLocking:
    """Verify that can_start_chat_turn acquires a row-level lock."""

    def test_source_calls_get_user_for_update(self) -> None:
        """The AST of can_start_chat_turn must contain a call to _get_user_for_update."""
        source = textwrap.dedent(inspect.getsource(CreditService.can_start_chat_turn))
        tree = ast.parse(source)

        calls: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                calls.append(node.attr)

        assert "_get_user_for_update" in calls, (
            "can_start_chat_turn must call _get_user_for_update to acquire "
            "a row-level lock (SELECT … FOR UPDATE) on the user row."
        )

    def test_get_user_for_update_uses_with_for_update(self) -> None:
        """_get_user_for_update must build a query with .with_for_update()."""
        source = textwrap.dedent(inspect.getsource(CreditService._get_user_for_update))
        assert "with_for_update" in source, (
            "_get_user_for_update must use .with_for_update() in its SELECT."
        )

    def test_can_start_chat_turn_does_not_use_plain_get_balance(self) -> None:
        """can_start_chat_turn must NOT fall back to the non-locking get_balance."""
        source = textwrap.dedent(inspect.getsource(CreditService.can_start_chat_turn))
        assert "get_balance" not in source, (
            "can_start_chat_turn should use _get_user_for_update (locking) "
            "instead of the plain get_balance (non-locking)."
        )


# ---------------------------------------------------------------------------
# 2. Runtime test: _get_user_for_update is actually invoked when the balance
#    path is reached (free tokens exhausted, must check credits).
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_can_start_chat_turn_invokes_locking_query_at_runtime(
    db_session: AsyncSession,
    credit_service: CreditService,
) -> None:
    """When free tokens are exhausted, can_start_chat_turn must invoke
    _get_user_for_update to lock the user row before reading the balance."""
    await _create_user(db_session, credits=5)
    # Exhaust free quota so the balance path is reached.
    await _create_chat_transaction(
        db_session,
        user_id="user-1",
        amount=0,
        total_tokens=200_000,
        balance_after=5,
    )

    with patch.object(
        CreditService,
        "_get_user_for_update",
        wraps=credit_service._get_user_for_update,
    ) as spy:
        result = await credit_service.can_start_chat_turn("user-1")

    assert result is True, "User with positive balance should be allowed."
    spy.assert_called_once_with("user-1")


@pytest.mark.asyncio
async def test_can_start_chat_turn_does_not_lock_when_under_free_quota(
    db_session: AsyncSession,
    credit_service: CreditService,
) -> None:
    """When a user is still under the free token quota, no row lock is needed."""
    await _create_user(db_session, credits=0)
    # Tokens are under the free quota so the balance path is NOT reached.
    await _create_chat_transaction(
        db_session,
        user_id="user-1",
        amount=0,
        total_tokens=100,
        balance_after=0,
    )

    with patch.object(
        CreditService,
        "_get_user_for_update",
        wraps=credit_service._get_user_for_update,
    ) as spy:
        result = await credit_service.can_start_chat_turn("user-1")

    assert result is True, "User under free quota should be allowed."
    spy.assert_not_called()


@pytest.mark.asyncio
async def test_can_start_chat_turn_blocks_zero_balance_with_locking(
    db_session: AsyncSession,
    credit_service: CreditService,
) -> None:
    """When free tokens are exhausted and balance is 0, should block (and
    still use the locking query)."""
    await _create_user(db_session, credits=0)
    await _create_chat_transaction(
        db_session,
        user_id="user-1",
        amount=0,
        total_tokens=200_000,
        balance_after=0,
    )

    with patch.object(
        CreditService,
        "_get_user_for_update",
        wraps=credit_service._get_user_for_update,
    ) as spy:
        result = await credit_service.can_start_chat_turn("user-1")

    assert result is False, "User with 0 balance after free quota should be blocked."
    spy.assert_called_once_with("user-1")
