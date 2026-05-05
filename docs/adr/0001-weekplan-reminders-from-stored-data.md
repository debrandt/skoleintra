# Week-plan reminders come from stored data

Skoleintra sends Sunday 09:00 Europe/Copenhagen reminders for upcoming Week plans from the stored published Week-plan data in PostgreSQL, not from whatever a scrape happens to fetch at reminder time. We chose this because reminders are a scheduled product behavior, not a side-effect of scraping, and tying them to live portal availability or scrape timing would make them unreliable and harder to reason about.
