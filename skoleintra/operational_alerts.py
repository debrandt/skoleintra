from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
import smtplib
from typing import Literal, Protocol

import requests
from sqlalchemy.orm import Session

from skoleintra.db.models import OperationalIncidentState
from skoleintra.settings import Settings, get_settings


AlertSeverity = Literal["critical", "partial"]
AlertStatus = Literal["failed", "recovered"]


@dataclass(slots=True)
class OperationalCheck:
    key: str
    subsystem: str
    scope: str | None
    severity: AlertSeverity
    status: AlertStatus
    summary: str
    detail: str


@dataclass(slots=True)
class OperationalAlert:
    key: str
    subsystem: str
    scope: str | None
    severity: AlertSeverity
    status: AlertStatus
    summary: str
    detail: str
    observed_at: datetime


@dataclass(slots=True)
class OperationalIncident:
    key: str
    subsystem: str
    scope: str | None
    severity: AlertSeverity
    summary: str
    detail: str
    active: bool
    first_failed_at: datetime | None
    last_failed_at: datetime | None
    last_alerted_at: datetime | None
    last_recovered_at: datetime | None


@dataclass(slots=True)
class AlertEmailConfig:
    host: str | None
    port: int
    username: str | None
    password: str | None
    sender: str | None
    recipients: list[str]
    use_ssl: bool
    starttls: bool

    @property
    def enabled(self) -> bool:
        return bool(self.host and self.sender and self.recipients)


@dataclass(slots=True)
class AlertNtfyConfig:
    url: str | None
    default_topic: str | None
    token: str | None

    @property
    def enabled(self) -> bool:
        return bool(self.url and self.default_topic)


class OperationalIncidentStore(Protocol):
    def get(self, key: str) -> OperationalIncident | None: ...

    def save(self, incident: OperationalIncident) -> None: ...


class OperationalAlertService:
    def __init__(self, store: OperationalIncidentStore) -> None:
        self._store = store

    def observe(
        self,
        check: OperationalCheck,
        *,
        observed_at: datetime,
    ) -> list[OperationalAlert]:
        incident = self._store.get(check.key)

        if check.status == "failed":
            return self._observe_failure(check, incident=incident, observed_at=observed_at)

        return self._observe_recovery(check, incident=incident, observed_at=observed_at)

    def _observe_failure(
        self,
        check: OperationalCheck,
        *,
        incident: OperationalIncident | None,
        observed_at: datetime,
    ) -> list[OperationalAlert]:
        if incident is None or not incident.active:
            next_incident = OperationalIncident(
                key=check.key,
                subsystem=check.subsystem,
                scope=check.scope,
                severity=check.severity,
                summary=check.summary,
                detail=check.detail,
                active=True,
                first_failed_at=observed_at,
                last_failed_at=observed_at,
                last_alerted_at=observed_at,
                last_recovered_at=incident.last_recovered_at if incident else None,
            )
            self._store.save(next_incident)
            return [self._to_alert(check, observed_at=observed_at)]

        next_incident = replace(
            incident,
            subsystem=check.subsystem,
            scope=check.scope,
            severity=check.severity,
            summary=check.summary,
            detail=check.detail,
            last_failed_at=observed_at,
        )

        if self._should_repeat_failure(next_incident, observed_at=observed_at):
            next_incident = replace(next_incident, last_alerted_at=observed_at)
            self._store.save(next_incident)
            return [self._to_alert(check, observed_at=observed_at)]

        self._store.save(next_incident)
        return []

    def _observe_recovery(
        self,
        check: OperationalCheck,
        *,
        incident: OperationalIncident | None,
        observed_at: datetime,
    ) -> list[OperationalAlert]:
        if incident is None or not incident.active:
            return []

        next_incident = replace(
            incident,
            summary=check.summary,
            detail=check.detail,
            active=False,
            last_recovered_at=observed_at,
        )
        self._store.save(next_incident)
        return [self._to_alert(check, observed_at=observed_at)]

    def _should_repeat_failure(
        self,
        incident: OperationalIncident,
        *,
        observed_at: datetime,
    ) -> bool:
        if incident.severity != "critical":
            return False
        if incident.last_alerted_at is None:
            return True
        return observed_at - incident.last_alerted_at >= timedelta(days=1)

    @staticmethod
    def _to_alert(check: OperationalCheck, *, observed_at: datetime) -> OperationalAlert:
        return OperationalAlert(
            key=check.key,
            subsystem=check.subsystem,
            scope=check.scope,
            severity=check.severity,
            status=check.status,
            summary=check.summary,
            detail=check.detail,
            observed_at=observed_at,
        )


class SqlOperationalIncidentStore:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, key: str) -> OperationalIncident | None:
        row = self._session.get(OperationalIncidentState, key)
        if row is None:
            return None
        return OperationalIncident(
            key=row.key,
            subsystem=row.subsystem,
            scope=row.scope,
            severity=row.severity,
            summary=row.summary,
            detail=row.detail,
            active=row.active,
            first_failed_at=row.first_failed_at,
            last_failed_at=row.last_failed_at,
            last_alerted_at=row.last_alerted_at,
            last_recovered_at=row.last_recovered_at,
        )

    def save(self, incident: OperationalIncident) -> None:
        row = self._session.get(OperationalIncidentState, incident.key)
        if row is None:
            row = OperationalIncidentState(key=incident.key)
            self._session.add(row)

        row.subsystem = incident.subsystem
        row.scope = incident.scope
        row.severity = incident.severity
        row.summary = incident.summary
        row.detail = incident.detail
        row.active = incident.active
        row.first_failed_at = incident.first_failed_at
        row.last_failed_at = incident.last_failed_at
        row.last_alerted_at = incident.last_alerted_at
        row.last_recovered_at = incident.last_recovered_at
        self._session.flush()


def read_operational_email_config(settings: Settings) -> AlertEmailConfig:
    port = settings.alert_smtp_port
    recipients = [
        part.strip()
        for part in settings.alert_email_to.split(",")
        if part.strip()
    ]
    return AlertEmailConfig(
        host=settings.alert_smtp_host or None,
        port=port,
        username=settings.alert_smtp_username or None,
        password=settings.alert_smtp_password or None,
        sender=settings.alert_email_from or None,
        recipients=recipients,
        use_ssl=settings.alert_smtp_use_ssl if settings.alert_smtp_use_ssl is not None else (port == 465),
        starttls=settings.alert_smtp_starttls if settings.alert_smtp_starttls is not None else (port != 465),
    )


def read_operational_ntfy_config(settings: Settings) -> AlertNtfyConfig:
    return AlertNtfyConfig(
        url=settings.alert_ntfy_url or None,
        default_topic=settings.alert_ntfy_topic or None,
        token=settings.alert_ntfy_token or None,
    )


def dispatch_operational_checks(
    session: Session,
    checks: list[OperationalCheck],
    *,
    settings: Settings | None = None,
    observed_at: datetime | None = None,
) -> list[OperationalAlert]:
    if not checks:
        return []

    current_settings = settings or get_settings()
    email_cfg = read_operational_email_config(current_settings)
    ntfy_cfg = read_operational_ntfy_config(current_settings)
    store = SqlOperationalIncidentStore(session)
    service = OperationalAlertService(store=store)
    run_observed_at = observed_at or datetime.now(timezone.utc)
    emitted: list[OperationalAlert] = []

    for check in checks:
        emitted.extend(service.observe(check, observed_at=run_observed_at))

    if not email_cfg.enabled and not ntfy_cfg.enabled:
        if emitted:
            print("alert: no channels configured; set ALERT_SMTP_*/ALERT_NTFY_* values in .env")
        return emitted

    for alert in emitted:
        if email_cfg.enabled:
            _send_operational_email(alert, email_cfg)
        if ntfy_cfg.enabled and ntfy_cfg.default_topic:
            _send_operational_ntfy(alert, ntfy_cfg, ntfy_cfg.default_topic)

    return emitted


def _send_operational_email(alert: OperationalAlert, cfg: AlertEmailConfig) -> None:
    if not cfg.enabled:
        raise RuntimeError("operational email channel is not configured")

    msg = EmailMessage()
    msg["From"] = cfg.sender
    msg["To"] = ", ".join(cfg.recipients)
    msg["Subject"] = _operational_subject(alert)
    msg.set_content(_operational_text(alert))

    if cfg.use_ssl:
        server: smtplib.SMTP | smtplib.SMTP_SSL = smtplib.SMTP_SSL(cfg.host, cfg.port, timeout=30)
    else:
        server = smtplib.SMTP(cfg.host, cfg.port, timeout=30)

    try:
        if not cfg.use_ssl and cfg.starttls:
            server.starttls()
        if cfg.username:
            if not cfg.password:
                raise RuntimeError("ALERT_SMTP_USERNAME is set but ALERT_SMTP_PASSWORD is missing")
            server.login(cfg.username, cfg.password)
        server.send_message(msg)
    finally:
        try:
            server.quit()
        except Exception:
            pass


def _send_operational_ntfy(alert: OperationalAlert, cfg: AlertNtfyConfig, topic: str) -> None:
    if not cfg.url:
        raise RuntimeError("operational ntfy url is missing")

    headers = {
        "Title": _operational_subject(alert),
        "Tags": ",".join(_operational_tags(alert)),
        "Markdown": "yes",
    }
    if cfg.token:
        headers["Authorization"] = f"Bearer {cfg.token}"

    response = requests.post(
        f"{cfg.url.rstrip('/')}/{topic}",
        data=_operational_markdown(alert).encode("utf-8"),
        headers=headers,
        timeout=20,
    )
    response.raise_for_status()


def _operational_subject(alert: OperationalAlert) -> str:
    return f"[Skoleintra:alert:{alert.severity}] {alert.summary}"


def _operational_text(alert: OperationalAlert) -> str:
    lines = [
        f"Severity: {alert.severity}",
        f"Status: {alert.status}",
        f"Subsystem: {alert.subsystem}",
    ]
    if alert.scope:
        lines.append(f"Scope: {alert.scope}")
    lines.append(f"Observed at: {alert.observed_at.isoformat()}")
    lines.append("")
    lines.append(alert.detail)
    return "\n".join(lines)


def _operational_markdown(alert: OperationalAlert) -> str:
    lines = [
        f"**{alert.summary}**",
        f"`{alert.severity}` • `{alert.status}` • `{alert.subsystem}`",
    ]
    if alert.scope:
        lines.append(f"Scope: `{alert.scope}`")
    lines.append(f"Observed: `{alert.observed_at.isoformat()}`")
    lines.append("")
    lines.append(alert.detail)
    return "\n".join(lines)


def _operational_tags(alert: OperationalAlert) -> list[str]:
    tags = ["warning" if alert.severity == "critical" else "information_source", "school"]
    if alert.status == "recovered":
        tags[0] = "white_check_mark"
    return tags
