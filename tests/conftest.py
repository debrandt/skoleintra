import pytest

from skoleintra.settings import Settings


@pytest.fixture
def operational_alert_settings() -> Settings:
    return Settings(
        smtp_host="content-smtp.example.test",
        email_from="content@example.test",
        email_to="parent@example.test",
        ntfy_url="https://content.ntfy.test",
        ntfy_topic="family-topic",
        alert_smtp_host="alert-smtp.example.test",
        alert_smtp_port=2525,
        alert_email_from="alerts@example.test",
        alert_email_to="ops1@example.test, ops2@example.test",
        alert_ntfy_url="https://alerts.ntfy.test",
        alert_ntfy_topic="ops-topic",
    )