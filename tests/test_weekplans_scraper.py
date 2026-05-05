import json
from datetime import datetime, timezone

from skoleintra.scraper.pages import weekplans


class DummyResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class DummyPortal:
    def __init__(
        self, pages: dict[str, str], hostname: str = "school.example.test"
    ) -> None:
        self._pages = pages
        self.hostname = hostname

    def abs_url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return f"https://{self.hostname}{path}"

    def get(self, url: str, **_kwargs) -> DummyResponse:
        return DummyResponse(self._pages[self.abs_url(url)])


def _detail_page(selected_plan: dict) -> str:
    payload = {"SelectedPlan": selected_plan}
    return (
        "<html><body>"
        f"<div id='root' data-clientlogic-settings-WeeklyPlansApp='{json.dumps(payload)}'></div>"
        "</body></html>"
    )


def test_scrape_returns_published_weekplan_with_normalized_content_and_links():
    child_url_prefix = "https://school.example.test/parent/1234/Freja"
    list_url = f"{child_url_prefix}item/weeklyplansandhomework/list"
    detail_url = (
        "https://school.example.test/parent/1234/Frejaitem/"
        "weeklyplansandhomework/show/19-2026"
    )
    portal = DummyPortal(
        {
            list_url: """
                <ul class="sk-weekly-plans-list-container">
                  <li><a href="/parent/1234/Frejaitem/weeklyplansandhomework/show/19-2026">Week 19</a></li>
                </ul>
            """,
            detail_url: _detail_page(
                {
                    "GeneralPlan": {
                        "Date": None,
                        "Day": None,
                        "DayOfWeek": 0,
                        "FormattedDate": None,
                        "LessonPlans": [
                            {
                                "Subject": {
                                    "Title": "General info",
                                    "FormattedTitle": "General info",
                                    "IsGeneralSubject": True,
                                },
                                "Content": "<p>Bring boots.</p>",
                                "Link": "https://links.example.test/menu",
                                "Snapshots": [],
                                "Attachments": [
                                    {
                                        "FileName": "Menu PDF",
                                        "Uri": "https://files.example.test/menu.pdf",
                                    }
                                ],
                                "IsDraft": False,
                            }
                        ],
                        "Schedule": None,
                    },
                    "DailyPlans": [
                        {
                            "Date": "2026-05-04",
                            "Day": "Mandag",
                            "DayOfWeek": 1,
                            "FormattedDate": "4. maj",
                            "LessonPlans": [
                                {
                                    "Subject": {
                                        "Title": "Nature",
                                        "FormattedTitle": "Nature",
                                        "IsGeneralSubject": False,
                                    },
                                    "Content": "<p>Plant seeds.</p>",
                                    "Link": "https://links.example.test/seeds",
                                    "Snapshots": [],
                                    "Attachments": [
                                        {
                                            "FileName": "Packing list",
                                            "Uri": "https://files.example.test/list.pdf",
                                        }
                                    ],
                                    "IsDraft": False,
                                }
                            ],
                            "Schedule": [],
                        }
                    ],
                    "FormattedWeek": "19-2026",
                    "ClassOrGroup": "Mellemtrin A",
                    "Attachments": [
                        {
                            "FileName": "Week overview",
                            "Uri": "https://files.example.test/overview.pdf",
                        }
                    ],
                }
            ),
        }
    )

    items = weekplans.scrape(portal, child_url_prefix)

    assert len(items) == 1
    item = items[0]
    assert item.type == "weekplan"
    assert item.external_id == "2026-W19"
    assert item.title == "Ugeplan for Mellemtrin A - uge 19"
    assert item.sender == "Mellemtrin A"
    assert item.date == datetime(2026, 5, 4, tzinfo=timezone.utc)
    assert "Bring boots." in item.body_html
    assert "Plant seeds." in item.body_html
    assert "Generelt" in item.body_html
    assert "Mandag" in item.body_html
    assert [attachment.url for attachment in item.attachments] == [
        "https://files.example.test/menu.pdf",
        "https://links.example.test/menu",
        "https://files.example.test/list.pdf",
        "https://links.example.test/seeds",
        "https://files.example.test/overview.pdf",
    ]


def test_scrape_ignores_draft_only_weekplans():
    child_url_prefix = "https://school.example.test/parent/1234/Freja"
    list_url = f"{child_url_prefix}item/weeklyplansandhomework/list"
    detail_url = (
        "https://school.example.test/parent/1234/Frejaitem/"
        "weeklyplansandhomework/show/20-2026"
    )
    portal = DummyPortal(
        {
            list_url: """
                <ul class="sk-weekly-plans-list-container">
                  <li><a href="/parent/1234/Frejaitem/weeklyplansandhomework/show/20-2026">Week 20</a></li>
                </ul>
            """,
            detail_url: _detail_page(
                {
                    "GeneralPlan": {
                        "Date": None,
                        "Day": None,
                        "DayOfWeek": 0,
                        "FormattedDate": None,
                        "LessonPlans": [
                            {
                                "Subject": {
                                    "Title": "General info",
                                    "FormattedTitle": "General info",
                                    "IsGeneralSubject": True,
                                },
                                "Content": "<p>Internal draft only.</p>",
                                "Link": "",
                                "Snapshots": [],
                                "Attachments": [],
                                "IsDraft": True,
                            }
                        ],
                        "Schedule": None,
                    },
                    "DailyPlans": [],
                    "FormattedWeek": "20-2026",
                    "ClassOrGroup": "Mellemtrin A",
                    "Attachments": [],
                }
            ),
        }
    )

    assert not weekplans.scrape(portal, child_url_prefix)
