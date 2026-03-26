"""Tests for credit service chat billing behavior."""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.database.models.credit import CreditTransaction, CreditTransactionType
from src.database.models.user import User
from src.services.credit_service import CreditService

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def async_engine():
    """Create an async engine backed by a single in-memory SQLite connection."""
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
    """Create a database session for credit service tests."""
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
    """Create a credit service instance."""
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


@pytest.mark.asyncio
async def test_consume_for_chat_usage_applies_free_quota_before_charging(
    db_session: AsyncSession,
    credit_service: CreditService,
) -> None:
    await _create_user(db_session, credits=10)
    await _create_chat_transaction(
        db_session,
        user_id="user-1",
        amount=0,
        total_tokens=95000,
        balance_after=10,
    )

    result = await credit_service.consume_for_chat_usage(
        user_id="user-1",
        token_usage={"input_tokens": 6000, "output_tokens": 4000, "total_tokens": 10000},
        model_name="gpt-4o",
        thread_id="thread-1",
    )

    assert result.free_tokens_applied == 5000
    assert result.billable_tokens == 5000
    assert result.credits_charged == 1
    assert result.historical_tokens_before == 95000
    assert result.historical_tokens_after == 105000
    assert result.charged is True
    assert await credit_service.get_balance("user-1") == 9


@pytest.mark.asyncio
async def test_can_start_chat_turn_blocks_when_free_quota_exhausted_and_balance_empty(
    db_session: AsyncSession,
    credit_service: CreditService,
) -> None:
    await _create_user(db_session, credits=0)
    await _create_chat_transaction(
        db_session,
        user_id="user-1",
        amount=0,
        total_tokens=100000,
        balance_after=0,
    )

    assert await credit_service.can_start_chat_turn("user-1") is False


@pytest.mark.asyncio
async def test_refund_consumption_releases_free_chat_tokens(
    db_session: AsyncSession,
    credit_service: CreditService,
) -> None:
    await _create_user(db_session, credits=3)

    result = await credit_service.consume_for_chat_usage(
        user_id="user-1",
        token_usage={"input_tokens": 4000, "output_tokens": 1000, "total_tokens": 5000},
        model_name="gpt-4o",
        thread_id="thread-1",
    )

    assert result.transaction_id is not None
    assert result.credits_charged == 0
    assert await credit_service.get_consumed_chat_tokens("user-1") == 5000

    refund = await credit_service.refund_consumption(
        user_id="user-1",
        original_transaction_id=result.transaction_id,
        reason="chat persist failed",
    )

    assert refund is not None
    assert refund.amount == 0
    assert await credit_service.get_balance("user-1") == 3
    assert await credit_service.get_consumed_chat_tokens("user-1") == 0


@pytest.mark.asyncio
async def test_consume_for_chat_usage_allows_single_turn_overdraft_then_blocks_next_turn(
    db_session: AsyncSession,
    credit_service: CreditService,
) -> None:
    await _create_user(db_session, credits=1)
    await _create_chat_transaction(
        db_session,
        user_id="user-1",
        amount=0,
        total_tokens=100000,
        balance_after=1,
    )

    result = await credit_service.consume_for_chat_usage(
        user_id="user-1",
        token_usage={"input_tokens": 15000, "output_tokens": 5000, "total_tokens": 20000},
        model_name="gpt-4o",
        thread_id="thread-1",
    )

    assert result.credits_charged == 2
    assert result.balance_after == -1
    assert result.charged is True
    assert await credit_service.get_balance("user-1") == -1
    assert await credit_service.can_start_chat_turn("user-1") is False
