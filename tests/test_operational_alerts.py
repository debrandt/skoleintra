from dataclasses import replace
from datetime import datetime, timedelta, timezone

import skoleintra.scraper as scraper_module
from skoleintra.operational_alerts import (
    OperationalAlertService,
    OperationalCheck,
    OperationalIncident,
    read_operational_email_config,
    read_operational_ntfy_config,
)
from skoleintra.settings import Settings


class MemoryIncidentStore:
    def __init__(self) -> None:
        self._incidents: dict[str, OperationalIncident] = {}

    def get(self, key: str) -> OperationalIncident | None:
        incident = self._incidents.get(key)
        if incident is None:
            return None
        return replace(incident)

    def save(self, incident: OperationalIncident) -> None:
        self._incidents[incident.key] = replace(incident)


def test_critical_scrape_login_failure_alerts_immediately_repeats_daily_and_recovers():
    service = OperationalAlertService(store=MemoryIncidentStore())
    first_seen = datetime(2026, 5, 5, 9, 0, tzinfo=timezone.utc)

    failure = OperationalCheck(
        key="scrape.login:aaskolen.m.skoleintra.dk",
        subsystem="scrape.login",
        scope="aaskolen.m.skoleintra.dk",
        severity="critical",
        status="failed",
        summary="Portal login failed",
        detail="Invalid login response from ForaeldreIntra",
    )

    initial_alerts = service.observe(failure, observed_at=first_seen)
    assert [
        (alert.status, alert.severity, alert.subsystem, alert.scope)
        for alert in initial_alerts
    ] == [("failed", "critical", "scrape.login", "aaskolen.m.skoleintra.dk")]

    same_day_alerts = service.observe(
        failure,
        observed_at=first_seen + timedelta(hours=12),
    )
    assert not same_day_alerts

    daily_repeat_alerts = service.observe(
        failure,
        observed_at=first_seen + timedelta(days=1, minutes=1),
    )
    assert [alert.status for alert in daily_repeat_alerts] == ["failed"]

    recovery = OperationalCheck(
        key=failure.key,
        subsystem=failure.subsystem,
        scope=failure.scope,
        severity=failure.severity,
        status="recovered",
        summary=failure.summary,
        detail="Portal login succeeded again",
    )
    recovery_alerts = service.observe(
        recovery,
        observed_at=first_seen + timedelta(days=1, minutes=2),
    )
    assert [(alert.status, alert.detail) for alert in recovery_alerts] == [
        ("recovered", "Portal login succeeded again")
    ]


def test_run_scrape_emits_structured_login_failure_check(monkeypatch):
    class DummyPortal:
        def __init__(self, hostname: str, state_dir: str) -> None:
            self.hostname = hostname
            self.state_dir = state_dir

    def fake_login(*args, **kwargs):
        raise RuntimeError("portal unavailable")

    monkeypatch.setattr(scraper_module, "PortalSession", DummyPortal)
    monkeypatch.setattr(scraper_module, "get_s3_client", lambda settings: None)
    monkeypatch.setattr(scraper_module, "login", fake_login)

    result = scraper_module.run_scrape(
        Settings(
            database_url="postgresql+psycopg://localhost/skoleintra",
            hostname="aaskolen.m.skoleintra.dk",
            username="parent",
            password="secret",
        ),
        debug=False,
    )

    assert result.errors == ["Login failed: portal unavailable"]
    assert [
        (check.status, check.severity, check.subsystem, check.scope)
        for check in result.operational_checks
    ] == [("failed", "critical", "scrape.login", "aaskolen.m.skoleintra.dk")]


def test_operational_alert_config_is_read_from_alert_specific_settings(
    operational_alert_settings: Settings,
):
    email_cfg = read_operational_email_config(operational_alert_settings)
    ntfy_cfg = read_operational_ntfy_config(operational_alert_settings)

    assert email_cfg.host == "alert-smtp.example.test"
    assert email_cfg.port == 2525
    assert email_cfg.sender == "alerts@example.test"
    assert email_cfg.recipients == ["ops1@example.test", "ops2@example.test"]
    assert ntfy_cfg.url == "https://alerts.ntfy.test"
    assert ntfy_cfg.default_topic == "ops-topic"
