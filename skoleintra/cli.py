import argparse
import os

from sqlalchemy.exc import OperationalError

from skoleintra.notifications import dispatch_notifications
import logging
import sys


def _configure_logging(debug: bool) -> None:
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        level=level,
        stream=sys.stderr,
    )
    # Quiet down noisy libraries unless in debug mode
    if not debug:
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("requests").setLevel(logging.WARNING)


def _cmd_migrate(args: argparse.Namespace) -> int:
    from alembic.config import Config
    from alembic import command as alembic_command
    from skoleintra.settings import get_settings

    settings = get_settings()
    if not settings.database_url:
        logging.error("Required environment variable not set: DATABASE_URL")
        return 1

    logging.info("Running database migrations…")
    cfg = Config()
    cfg.set_main_option("script_location", "skoleintra.db:migrations")
    cfg.set_main_option("sqlalchemy.url", settings.database_url)
    alembic_command.upgrade(cfg, "head")
    logging.info("Migrations complete.")
    return 0


def _cmd_scrape(args: argparse.Namespace) -> int:
    from skoleintra.db import init_db
    from skoleintra.photos import parse_not_older_than_date
    from skoleintra.scraper import run_scrape
    from skoleintra.settings import get_settings

    settings = get_settings()

    missing: list[str] = []
    if not settings.database_url:
        missing.append("DATABASE_URL")
    if not settings.hostname:
        missing.append("SKOLEINTRA_HOSTNAME")
    if not settings.username:
        missing.append("SKOLEINTRA_USERNAME")
    if not settings.password:
        missing.append("SKOLEINTRA_PASSWORD")
    if missing:
        for name in missing:
            logging.error("Required environment variable not set: %s", name)
        return 1

    init_db(settings.database_url)

    try:
        not_older_than = parse_not_older_than_date(
            args.photos_not_older_than or settings.photos_not_older_than
        )
    except ValueError as exc:
        logging.error("Invalid --photos-not-older-than value: %s", exc)
        return 2

    retention_days = (
        args.photo_retention_days
        if args.photo_retention_days is not None
        else settings.photo_retention_days
    )

    result = run_scrape(
        settings,
        debug=args.debug,
        photo_not_older_than=not_older_than,
        photo_retention_days=retention_days,
    )

    print(
        f"\nScrape complete:"
        f"\n  children : {result.children_found}"
        f"\n  new items: {result.items_new}"
        f"\n  updated  : {result.items_updated}"
        f"\n  attachments: {result.attachments}"
        f"\n  blobs uploaded: {result.blobs_uploaded}"
        f"\n  photo blobs downloaded: {result.photo_blobs_downloaded}"
        f"\n  photo blobs skipped (old): {result.photo_blobs_skipped_old}"
        f"\n  photo blobs skipped (non-photo): {result.photo_blobs_skipped_non_photo}"
        f"\n  photo blobs pruned: {result.photo_blobs_pruned}"
    )
    if result.errors:
        print(f"\n  errors ({len(result.errors)}):")
        for err in result.errors:
            print(f"    - {err}")
        return 1
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="skoleintra")

    sub = parser.add_subparsers(dest="command")

    sub.add_parser("migrate", help="Apply database migrations (alembic upgrade head)")

    scrape_p = sub.add_parser("scrape", help="Run scraper once")
    scrape_p.add_argument(
        "--debug",
        action="store_true",
        default=False,
        help="Enable debug logging and save failure artifacts to state_dir",
    )
    scrape_p.add_argument(
        "--photos-not-older-than",
        default="",
        help="Only download photo blobs for items dated on/after YYYY-MM-DD",
    )
    scrape_p.add_argument(
        "--photo-retention-days",
        type=int,
        default=None,
        help="Delete stored photo blobs older than N days before scrape processing",
    )

    notify = sub.add_parser("notify", help="Send pending notifications")
    notify.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum number of pending items to process (default: 50)",
    )
    notify.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be sent without dispatching",
    )
    notify.add_argument(
        "--debug",
        action="store_true",
        help="Enable verbose notification logs",
    )

    web = sub.add_parser("web", help="Start web UI")
    web.add_argument("--host", default="127.0.0.1", help="Host bind address")
    web.add_argument("--port", type=int, default=8000, help="Port to listen on")
    web.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for local development",
    )

    args = parser.parse_args()

    # --debug can appear before or after the subcommand; merge both
    debug = getattr(args, "debug", False)
    _configure_logging(debug)

    if args.command == "migrate":
        sys.exit(_cmd_migrate(args))
    elif args.command == "scrape":
        sys.exit(_cmd_scrape(args))
    elif args.command == "notify":
        try:
            result = dispatch_notifications(
                limit=args.limit,
                dry_run=args.dry_run,
                debug=args.debug,
            )
        except OperationalError as exc:
            print(f"notify: database connection failed: {exc}")
            print("notify: set DATABASE_URL to a reachable Postgres instance")
            raise SystemExit(2)
        print(
            "notify: "
            f"bootstrap_created={result.bootstrap_created} "
            f"processed={result.processed} "
            f"sent={result.sent} "
            f"skipped={result.skipped} "
            f"failed={result.failed}"
        )
        if result.failed > 0:
            raise SystemExit(1)
    elif args.command == "web":
        from skoleintra.db import init_db
        from skoleintra.settings import get_settings

        settings = get_settings()
        if not settings.database_url:
            print("web: DATABASE_URL is required")
            sys.exit(2)

        init_db(settings.database_url)

        import uvicorn

        workers = 1 if args.reload else max(1, int(os.getenv("WEB_CONCURRENCY", "1")))
        uvicorn.run(
            "skoleintra.web:create_app",
            factory=True,
            host=args.host,
            port=args.port,
            reload=args.reload,
            workers=workers,
        )
    else:
        parser.print_help()
        sys.exit(0)


if __name__ == "__main__":
    main()