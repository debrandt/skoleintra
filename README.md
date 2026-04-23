# Skoleintra

Continuously scrapes [ForældreIntra](https://www.foraldreintra.dk/) into
PostgreSQL, with a planned web UI and notification dispatcher.

---

## Required environment variables

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string, e.g. `postgresql+psycopg://user:pass@localhost:5432/skoleintra` |
| `SKOLEINTRA_HOSTNAME` | Your school's ForældreIntra hostname, e.g. `aaskolen.m.skoleintra.dk` |
| `SKOLEINTRA_USERNAME` | Portal username |
| `SKOLEINTRA_PASSWORD` | Portal password |
| `SKOLEINTRA_LOGIN_TYPE` | `uni` (UNI-Login, default) or `alm` (ordinary login) |
| `SKOLEINTRA_PHOTOS_NOT_OLDER_THAN` | Optional cutoff date (`YYYY-MM-DD`) for photo blob downloads |
| `SKOLEINTRA_PHOTO_RETENTION_DAYS` | Optional retention window for stored photo blobs |

### Optional

| Variable | Description | Default |
|---|---|---|
| `SKOLEINTRA_STATE_DIR` | Directory for cookie jar and debug artifacts | `~/.skoleintra` |
| `SMTP_HOST` | SMTP server hostname (Phase 3) | — |
| `SMTP_PORT` | SMTP server port (Phase 3) | — |
| `SMTP_USERNAME` | SMTP username (Phase 3) | — |
| `SMTP_PASSWORD` | SMTP password (Phase 3) | — |
| `EMAIL_FROM` | Sender address (Phase 3) | — |
| `EMAIL_TO` | Recipient address (Phase 3) | — |
| `NTFY_URL` | ntfy server URL (Phase 3) | — |
| `NTFY_TOPIC` | ntfy topic (Phase 3) | — |

---

## Usage

### Run the scraper once

```sh
DATABASE_URL="postgresql+psycopg://user:pass@localhost/skoleintra" \
SKOLEINTRA_HOSTNAME="school.foraldreintra.dk" \
SKOLEINTRA_USERNAME="myuser" \
SKOLEINTRA_PASSWORD="mypassword" \
skoleintra scrape
```

Add `--debug` for verbose logging and failure artifact saving:

```sh
skoleintra scrape --debug
```

Photo blob controls are part of the same scrape command:

```sh
skoleintra scrape \
    --photos-not-older-than 2026-01-01 \
    --photo-retention-days 30
```

### Apply database migrations

```sh
DATABASE_URL="..." alembic upgrade head
```

---

## Development

### Install dependencies

```sh
pip install -e .
```

### Database setup (local Postgres)

```sh
createdb skoleintra
DATABASE_URL="postgresql+psycopg://localhost/skoleintra" alembic upgrade head
```

---

## Architecture overview

```
systemd timer ──► skoleintra scrape
                    ├─ login (requests.Session + cookie persistence)
                    ├─ discover children
                    ├─ scrape messages
                    └─ upsert into PostgreSQL

(Phase 3) skoleintra notify ──► send email / ntfy for new items
(Phase 4) skoleintra web    ──► FastAPI web UI
```

See [`PRODUCT_PLAN.md`](PRODUCT_PLAN.md) for the full phased roadmap.
