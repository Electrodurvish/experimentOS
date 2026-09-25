from unittest.mock import MagicMock, patch

from apps.observability.errors import setup_sentry, tag_experiment


class TestSetupSentry:
    def test_disabled_without_dsn(self, settings):
        settings.SENTRY_DSN = ""
        assert setup_sentry() is False

    def test_initializes_with_dsn(self, settings):
        settings.SENTRY_DSN = "https://public@example.ingest.sentry.io/1"
        with patch("sentry_sdk.init") as mock_init:
            assert setup_sentry() is True
        kwargs = mock_init.call_args.kwargs
        assert kwargs["dsn"] == settings.SENTRY_DSN
        assert kwargs["send_default_pii"] is False


class TestTagExperiment:
    def test_sets_tags(self):
        with patch("sentry_sdk.set_tag") as mock_tag:
            tag_experiment("checkout_v3", "treatment", 4)
        mock_tag.assert_any_call("experiment.key", "checkout_v3")
        mock_tag.assert_any_call("experiment.variant", "treatment")
        mock_tag.assert_any_call("experiment.version", "4")

    def test_never_raises(self):
        with patch("sentry_sdk.set_tag", MagicMock(side_effect=RuntimeError)):
            tag_experiment("checkout_v3")
