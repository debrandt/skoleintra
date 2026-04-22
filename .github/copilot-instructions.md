# Copilot Instructions

## Product intent

Skoleintra exists to replace manual logins to ForældreIntra by continuously syncing data into PostgreSQL, exposing a web UI, and sending notifications.

## First steps in this repository

1. Read `README.md` for runtime expectations and environment variables.
2. Use Nix-based commands (do **not** start with ad-hoc `pip install` workflows):
   - Run tests: `nix develop -c pytest`
   - Run CLI commands: `nix run . -- <command>`
   - Example notifier dry-run: `nix run . -- notify --dry-run`
3. Keep changes small and focused; this codebase is early-stage and intentionally simple.

## Project map

- CLI entrypoint: `skoleintra/cli.py` (`migrate`, `scrape`, `notify`, `web`)
- Runtime settings: `skoleintra/settings.py` (Pydantic settings from env/.env)
- Scrape orchestrator: `skoleintra/scraper/__init__.py`
- Message scraper/parser: `skoleintra/scraper/pages/messages.py`
- DB models/upsert logic: `skoleintra/db/models.py`, `skoleintra/db/upsert.py`
- Notifications: `skoleintra/notifications/dispatcher.py`
- Web app/routes: `skoleintra/web/__init__.py`, `skoleintra/web/routes/__init__.py`
- Tests: `tests/` (currently scraper parsing-focused tests)

## Change expectations

- Preserve idempotent scraping/upsert behavior (unique keys and upsert flow are core).
- Keep notification deduplication behavior intact (`notify_sent` and channel-level `_notify` state in `raw_json`).
- If DB models change, add/update Alembic migrations in `skoleintra/db/migrations/`.
- Prefer extending existing modules over introducing new layers unless clearly necessary.

## Notification content policy (strict)

- Do not truncate or summarize message bodies in notifications.
- Do not implement preview-style message delivery by default.
- Preserve full message content so users can rely on notifications as the primary reading surface.
- Any feature that reduces message completeness is a regression unless explicitly requested.

## Troubleshooting and known issues

- **Issue encountered:** shell commands in this agent session may hang with no output (including `nix develop -c pytest`), and returned shell IDs may be unreadable.
  - **Work-around used:** verify command conventions from repository config (`flake.nix`, CI workflow) and continue with file-level changes when command execution is unavailable.
- If `nix run . -- ...` fails locally, confirm Nix flakes are enabled and run from repo root: `/home/runner/work/skoleintra/skoleintra`.
