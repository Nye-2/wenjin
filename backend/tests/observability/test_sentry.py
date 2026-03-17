"""Tests for Sentry initialization."""

from unittest.mock import MagicMock, patch

from src.observability.sentry import init_sentry


class TestInitSentry:
    def test_skips_when_disabled(self):
        with patch("src.observability.sentry.get_sentry_settings") as mock_settings:
            mock_settings.return_value = MagicMock(enabled=False, dsn="")
            init_sentry()

    def test_skips_when_no_dsn(self):
        with patch("src.observability.sentry.get_sentry_settings") as mock_settings:
            mock_settings.return_value = MagicMock(enabled=True, dsn="")
            init_sentry()

    @patch("sentry_sdk.init")
    def test_initializes_when_enabled_with_dsn(self, mock_init):
        with patch("src.observability.sentry.get_sentry_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                enabled=True,
                dsn="https://examplePublicKey@o0.ingest.sentry.io/0",
                environment="test",
                traces_sample_rate=0.1,
                profiles_sample_rate=0.1,
            )
            init_sentry()
            mock_init.assert_called_once()
            call_kwargs = mock_init.call_args[1]
            assert call_kwargs["dsn"] == "https://examplePublicKey@o0.ingest.sentry.io/0"
            assert call_kwargs["environment"] == "test"
