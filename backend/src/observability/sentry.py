"""Sentry error monitoring initialization."""

import logging

from src.config.app_config import get_sentry_settings

logger = logging.getLogger(__name__)


def init_sentry() -> None:
    """Initialize Sentry SDK if enabled and DSN is configured."""
    sentry_settings = get_sentry_settings()
    if not sentry_settings.enabled or not sentry_settings.dsn:
        logger.info("Sentry disabled or DSN not configured, skipping init")
        return

    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.redis import RedisIntegration
    from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

    sentry_sdk.init(
        dsn=sentry_settings.dsn,
        environment=sentry_settings.environment,
        traces_sample_rate=sentry_settings.traces_sample_rate,
        profiles_sample_rate=sentry_settings.profiles_sample_rate,
        integrations=[
            FastApiIntegration(),
            SqlalchemyIntegration(),
            RedisIntegration(),
        ],
    )
    logger.info("Sentry initialized (env=%s)", sentry_settings.environment)
