"""Week plan scraper for ForaeldreIntra."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from html import escape

from bs4 import BeautifulSoup

from skoleintra.scraper.models import ScrapedAttachment, ScrapedItem
from skoleintra.scraper.session import PortalSession

logger = logging.getLogger(__name__)

ITEM_TYPE = "weekplan"


def scrape(portal: PortalSession, child_url_prefix: str) -> list[ScrapedItem]:
    """Scrape published week plans for one child."""
    url = f"{child_url_prefix}item/weeklyplansandhomework/list"
    logger.info("Fetching week plans from %s", url)
    resp = portal.get(url)
    soup = BeautifulSoup(resp.text, "lxml")

    items: list[ScrapedItem] = []
    seen_urls: set[str] = set()
    for plan_link in soup.select("ul.sk-weekly-plans-list-container a[href]"):
        plan_url = portal.abs_url((plan_link.get("href") or "").strip())
        if not plan_url or plan_url in seen_urls:
            continue
        seen_urls.add(plan_url)

        if not plan_url.startswith(child_url_prefix):
            logger.debug("Skipping out-of-scope week plan URL: %s", plan_url)
            continue

        try:
            detail_resp = portal.get(plan_url)
        except Exception as exc:
            logger.warning("Failed to fetch week plan %s: %s", plan_url, exc)
            continue

        item = _scraped_item_from_detail(detail_resp.text, plan_url)
        if item is not None:
            items.append(item)

    logger.info("Found %d week plan item(s) for %s", len(items), child_url_prefix)
    return items


def _scraped_item_from_detail(page_html: str, plan_url: str) -> ScrapedItem | None:
    selected_plan = _selected_plan_from_html(page_html)
    if selected_plan is None:
        return None

    visible_sections = _visible_sections(selected_plan)
    plan_attachments = _plan_attachments(selected_plan)
    if not visible_sections and not plan_attachments:
        return None

    group_name = str(selected_plan.get("ClassOrGroup") or "SkoleIntra")
    formatted_week = str(selected_plan.get("FormattedWeek") or "")
    external_id = _external_id_for(selected_plan, plan_url)
    title = _title_for(group_name, formatted_week, external_id)

    attachments = [
        attachment
        for _, lesson_plans in visible_sections
        for lesson_plan in lesson_plans
        for attachment in _lesson_plan_attachments(lesson_plan)
    ]
    attachments.extend(plan_attachments)

    return ScrapedItem(
        type=ITEM_TYPE,
        external_id=external_id,
        title=title,
        sender=group_name,
        body_html=_body_html_for(title, visible_sections),
        date=_date_for(selected_plan),
        raw_json=_raw_json_for(selected_plan, plan_url),
        attachments=attachments,
    )


def _selected_plan_from_html(page_html: str) -> dict | None:
    soup = BeautifulSoup(page_html, "lxml")
    root = soup.select_one("#root")
    if root is None:
        return None

    raw = None
    for attr_name, attr_value in root.attrs.items():
        if attr_name.lower() == "data-clientlogic-settings-weeklyplansapp":
            raw = attr_value
            break
    if not isinstance(raw, str) or not raw:
        return None

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None

    selected_plan = payload.get("SelectedPlan")
    return selected_plan if isinstance(selected_plan, dict) else None


def _visible_sections(selected_plan: dict) -> list[tuple[str, list[dict]]]:
    sections: list[tuple[str, list[dict]]] = []

    general_plan = selected_plan.get("GeneralPlan")
    if isinstance(general_plan, dict):
        lesson_plans = _visible_lesson_plans(general_plan)
        if lesson_plans:
            sections.append(("Generelt", lesson_plans))

    for daily_plan in selected_plan.get("DailyPlans") or []:
        if not isinstance(daily_plan, dict):
            continue
        lesson_plans = _visible_lesson_plans(daily_plan)
        if not lesson_plans:
            continue
        sections.append((str(daily_plan.get("Day") or "Dag"), lesson_plans))

    return sections


def _visible_lesson_plans(plan: dict) -> list[dict]:
    lesson_plans: list[dict] = []
    for lesson_plan in plan.get("LessonPlans") or []:
        if not isinstance(lesson_plan, dict):
            continue
        if lesson_plan.get("IsDraft"):
            continue
        lesson_plans.append(lesson_plan)
    return lesson_plans


def _body_html_for(title: str, sections: list[tuple[str, list[dict]]]) -> str:
    parts = [f"<h2>{escape(title)}</h2>"]
    for section_title, lesson_plans in sections:
        parts.append("<section>")
        parts.append(f"<h3>{escape(section_title)}</h3>")
        for lesson_plan in lesson_plans:
            subject = _subject_for(lesson_plan)
            if subject:
                parts.append(f"<h4>{escape(subject)}</h4>")
            content = str(lesson_plan.get("Content") or "").strip()
            if content:
                parts.append(content)
        parts.append("</section>")
    return "\n".join(parts)


def _subject_for(lesson_plan: dict) -> str:
    subject = lesson_plan.get("Subject")
    if not isinstance(subject, dict):
        return ""
    return str(
        subject.get("FormattedTitle") or subject.get("Title") or "Uden angivelse af fag"
    )


def _lesson_plan_attachments(lesson_plan: dict) -> list[ScrapedAttachment]:
    attachments: list[ScrapedAttachment] = []
    for entry in lesson_plan.get("Attachments") or []:
        attachment = _attachment_from_entry(entry)
        if attachment is not None:
            attachments.append(attachment)

    link = str(lesson_plan.get("Link") or "").strip()
    if link:
        attachments.append(
            ScrapedAttachment(
                filename=_subject_for(lesson_plan) or "Link",
                url=link,
            )
        )
    return attachments


def _plan_attachments(selected_plan: dict) -> list[ScrapedAttachment]:
    attachments: list[ScrapedAttachment] = []
    for entry in selected_plan.get("Attachments") or []:
        attachment = _attachment_from_entry(entry)
        if attachment is not None:
            attachments.append(attachment)
    return attachments


def _attachment_from_entry(entry: object) -> ScrapedAttachment | None:
    if not isinstance(entry, dict):
        return None
    url = str(entry.get("Uri") or "").strip()
    if not url:
        return None
    filename = str(entry.get("FileName") or url).strip() or url
    return ScrapedAttachment(filename=filename, url=url)


def _date_for(selected_plan: dict) -> datetime | None:
    for daily_plan in selected_plan.get("DailyPlans") or []:
        if not isinstance(daily_plan, dict):
            continue
        raw = str(daily_plan.get("Date") or "").strip()
        if not raw:
            continue
        try:
            return datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _external_id_for(selected_plan: dict, plan_url: str) -> str:
    formatted_week = str(selected_plan.get("FormattedWeek") or "").strip()
    match = re.fullmatch(r"(\d{1,2})-(\d{4})", formatted_week)
    if match:
        week, year = match.groups()
        return f"{year}-W{int(week):02d}"

    plan_date = _date_for(selected_plan)
    if plan_date is not None:
        iso_year, iso_week, _ = plan_date.isocalendar()
        return f"{iso_year}-W{iso_week:02d}"

    return hashlib.sha1(plan_url.encode("utf-8")).hexdigest()


def _title_for(group_name: str, formatted_week: str, external_id: str) -> str:
    match = re.fullmatch(r"(\d{1,2})-(\d{4})", formatted_week)
    if match:
        week, _ = match.groups()
        return f"Ugeplan for {group_name} - uge {int(week)}"
    return f"Ugeplan for {group_name} - {external_id}"


def _raw_json_for(selected_plan: dict, plan_url: str) -> dict:
    raw = {
        key: value
        for key, value in selected_plan.items()
        if key not in {"HistoryData", "StudentName"}
    }
    raw["plan_url"] = plan_url
    return raw
