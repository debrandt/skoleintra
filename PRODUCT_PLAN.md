# Skoleintra Product Plan (starting Phase 2)

This document describes the execution plan for building **Skoleintra** into a reliable system that:
- Continuously syncs data from ForældreIntra (or related endpoints) into PostgreSQL
- Provides a Web UI for browsing/sorting/marking items and managing notification preferences
- Sends notifications (email and/or ntfy) for relevant events
- Runs cleanly on NixOS (`wh-server`) with systemd units and secrets managed via agenix

**Current status (as of 2026-04-22):**
- Project scaffolding exists
- CLI entrypoint works
- DB models exist and Alembic is set up (autogenerate configured via `Base.metadata`)

---

## Goals

### Primary goals
- **Continuous sync**: periodic scraping with robust deduplication and minimal noise.
- **Structured storage**: normalize scraped content into Postgres tables (items, children, attachments).
- **Web UI**: browse/sort/filter, mark read/unread, view item detail, search.
- **Notifications**: email and/or ntfy, per-type toggles, no duplicates.
- **NixOS deploy**: declarative service + timer + Caddy reverse proxy; secrets via agenix.

### Non-goals (for now)
- Full fidelity archiving of *all* portal resources forever (start with “useful” subsets).
- Supporting many schools/tenants simultaneously (design should not prevent it, but not required initially).
- Building a complex SPA if server-rendered + htmx meets needs.
- Bypassing CAPTCHA/2FA protections; if required, we may need a different strategy.

---

## Architecture overview

### Components
1. **Scraper (CLI, scheduled)**  
   - Runs periodically (systemd timer on wh-server)
   - Logs in, fetches relevant pages, parses items
   - Upserts into Postgres
   - Marks items as “needs notification” when newly discovered

2. **Database (PostgreSQL)**  
   - Source of truth for all scraped items and user state (read/unread, preferences)

3. **Notification dispatcher**  
   - Sends notifications for items not yet notified
   - Uses `notification_settings` (per type) + optional per-item rules later

4. **Web UI (FastAPI)**  
   - Item list views with sorting/filtering
   - Item detail
   - Settings pages (notification toggles, scrape interval later)

5. **Reverse proxy (Caddy on wh-server)**  
   - TLS termination and routing to web app

### Data flow
```
systemd timer -> skoleintra scrape
  -> login + fetch -> parse -> upsert (items/attachments)
  -> mark new items notify_sent=false
optional: skoleintra notify
  -> select items notify_sent=false -> send -> set notify_sent=true
web app reads DB and updates is_read/preferences
```

---

## Configuration & secrets

### Required runtime environment variables
- `DATABASE_URL`  
  Example: `postgresql+psycopg://USER:PASSWORD@HOST:5432/DBNAME`

- `SKOLEINTRA_HOSTNAME`  
  e.g. `example.foraldreintra.dk` (actual hostname depends on school)

- `SKOLEINTRA_USERNAME`
- `SKOLEINTRA_PASSWORD`
- `SKOLEINTRA_LOGIN_TYPE`  
  Values: `uni` or `alm` (ordinary). Default TBD.

### Optional environment variables
- `SKOLEINTRA_STATE_DIR`  
  Location for cookie jar/state and cached pages (when enabled).  
  On NixOS service: prefer systemd `StateDirectory=skoleintra`.

- Email:
  - `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`
  - `EMAIL_FROM`, `EMAIL_TO`

- ntfy:
  - `NTFY_URL` (e.g. `https://ntfy.whildebrandt.dk`)
  - `NTFY_TOPIC` (default topic for messages)

### Secrets management on wh-server (NixOS)
- Use **agenix** for:
  - `skoleintra-credentials.env` (EnvironmentFile for systemd units)
  - optional SMTP credentials

---

## Data model summary

Tables (current intent):
- `children`
  - `id`, `name`, `school_hostname`, timestamps
- `items`
  - `id`, `child_id`, `type`, `external_id`, `title`, `sender`, `body_html`, `date`
  - `is_read`, `notify_sent`, `raw_json`, timestamps
  - unique constraint: `(child_id, type, external_id)`
- `attachments`
  - `id`, `item_id`, `filename`, `url`, `local_path`, timestamps
- `notification_settings`
  - `type` (PK), `email_enabled`, `ntfy_enabled`, `ntfy_topic`

---

# Phased milestones

## Phase 2 — Scraper MVP (login + one “high-value” section + DB upsert)

### Outcomes
- `skoleintra scrape` performs:
  - login
  - fetch/parse one section (start with **messages/dialogue** or **frontpage**)
  - write to DB
  - prints a run summary

### Deliverables
- `skoleintra/scraper/` modules:
  - browser/session helper (requests.Session + headers)
  - login flow (UNI or alm)
  - 1 page scraper module (messages recommended)
- DB upsert helpers:
  - `upsert_child()`, `upsert_item()`, `upsert_attachment()`
- Basic state handling:
  - persist cookies/state to a writable directory
  - store last failure HTML for debugging

### Checklist
- [ ] Decide first “page” to implement (messages vs documents/weekplans)
- [ ] Implement requests-based session wrapper
- [ ] Implement login flow with redirect/form handling
- [ ] Implement first page parser
- [ ] Define an internal scraped-item DTO (dataclass or pydantic model)
- [ ] Upsert scraped items into Postgres
- [ ] Add CLI command `skoleintra scrape` with meaningful logging
- [ ] Add `--debug` flag and failure artifact saving
- [ ] Document required env vars in README

### Acceptance test
- Run: `DATABASE_URL=... SKOLEINTRA_*... skoleintra scrape`
- DB shows new rows in `items`
- Re-running does not duplicate items (idempotent)

---

## Phase 3 — Notifications (email + ntfy, deduped)

### Outcomes
- New items trigger notifications exactly once.
- User can disable notifications per type.

### Deliverables
- Notification dispatcher command:
  - `skoleintra notify` (or integrated into `scrape`)
- Email sender using SMTP (configurable)
- ntfy sender via HTTP POST
- Update `notify_sent` after success
- Add `notification_settings` defaults (migration or bootstrapping)

### Checklist
- [ ] Define which item types generate notifications by default
- [ ] Implement ntfy sender
- [ ] Implement SMTP email sender
- [ ] Implement “select unsent notifications” query
- [ ] Update DB to mark `notify_sent=true` after sending
- [ ] Add retry/backoff and failure visibility

---

## Phase 4 — Web UI (browse, search, mark read, settings)

### Outcomes
- Browse items by child/type/date.
- Mark read/unread and filter unread.
- Manage notification toggles per type.
- (Optional) keyword search.

### Deliverables
- FastAPI app
- Jinja templates + htmx (preferred for simplicity)
- Routes:
  - `GET /` dashboard
  - `GET /items` list with filters/sort
  - `GET /items/{id}` detail
  - `POST/PATCH /items/{id}/read` toggle
  - `GET/POST /settings/notifications`

### Checklist
- [ ] Add DB session dependency injection for FastAPI
- [ ] Create list/detail templates
- [ ] Implement filtering/sorting
- [ ] Implement mark read/unread
- [ ] Implement settings UI for notification toggles
- [ ] Add pagination

---

## Phase 5 — NixOS integration on wh-server (service + timer + Caddy)

### Outcomes
- Fully declarative deployment on `debrandt/wh-server`.
- Runs on a schedule and exposes web UI under a virtual host.

### Deliverables
- NixOS module `wh-server/modules/skoleintra.nix`:
  - systemd `skoleintra-web`
  - systemd `skoleintra-scrape` + timer
  - Postgres ensure DB + user
  - EnvironmentFile from agenix secret
- Caddy config entry:
  - reverse proxy to FastAPI port
- Firewall rules if needed (likely via Tailscale interface)

### Checklist
- [ ] Add agenix secret for creds
- [ ] Add systemd units
- [ ] Add timer cadence (start with 15min)
- [ ] Add Caddy vhost
- [ ] Confirm logs in journald and state in `/var/lib/skoleintra` (StateDirectory)
- [ ] Add health endpoint for Gatus (optional)

---

## Phase 6 — Hardening & Ops (reliability, resilience, maintainability)

### Outcomes
- Scraper resilient to HTML changes and transient errors.
- No silent failures.
- Safe upgrades.

### Work items
- [ ] Robust parsing with fallbacks (don’t crash on missing fields)
- [ ] HTTP retry policy and timeouts everywhere
- [ ] Rate limiting / polite scraping
- [ ] Structured logging, log redaction of secrets
- [ ] Metrics: last successful scrape timestamp; counts
- [ ] Alerting via ntfy on repeated failures
- [ ] Regression fixtures: saved HTML samples + unit tests for parsers
- [ ] Database migrations integrated into deployment (alembic upgrade)
- [ ] Consider Playwright login fallback if requests stops working

---

## Testing strategy

### Unit tests
- Parser tests using saved HTML fixtures:
  - `tests/fixtures/*.html`
  - ensure extracted items match expected normalized output

### Integration tests (local)
- With a test Postgres DB:
  - run `skoleintra scrape` against recorded fixtures (or mocked HTTP)
  - verify DB upsert and dedupe

### Manual acceptance
- Real login test against portal
- Confirm no duplicate notifications
- Confirm web UI correctness

---

## Rollout plan

1. **Local dev**: implement Phase 2 against real portal with verbose logging.
2. **Local DB**: confirm dedupe; keep scrape cadence low.
3. **wh-server staging**: deploy scraper-only (no web UI) + DB.
4. **Enable notifications**: ntfy first (easy to observe), then email.
5. **Enable web UI**: add Caddy vhost, test authentication decision (see open questions).
6. **Increase scrape cadence**: based on portal tolerance and stability.

---

## Open questions / risks

### Login stability
- UNI-login pages can change and sometimes require JS.
- CAPTCHA / 2FA may break non-browser automation.
- Plan: start with requests; if it fails, evaluate Playwright.

### HTML & endpoint churn
- Page structure can change without notice.
- Plan: fixtures + parser tests + graceful degradation.

### Rate limiting / account lockout
- Too frequent scraping could trigger protection.
- Plan: moderate cadence (15–60 min), backoff on errors, avoid repeated failed logins.

### Multi-child & multiple accounts
- If you ever need more than one account or more than one school hostname:
  - adjust uniqueness constraints for `children`
  - support multiple configured “accounts”

### Web UI access control
- Should UI be:
  - Tailscale-only,
  - behind Caddy basic auth,
  - or have app-level auth?
- Decide before exposing publicly.

---
