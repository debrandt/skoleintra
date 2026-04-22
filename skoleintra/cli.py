import argparse

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


def _cmd_scrape(args: argparse.Namespace) -> int:
    from skoleintra.db import init_db
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

    result = run_scrape(settings, debug=args.debug)

    print(
        f"\nScrape complete:"
        f"\n  children : {result.children_found}"
        f"\n  new items: {result.items_new}"
        f"\n  updated  : {result.items_updated}"
        f"\n  attachments: {result.attachments}"
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

    scrape_p = sub.add_parser("scrape", help="Run scraper once")
    scrape_p.add_argument(
        "--debug",
        action="store_true",
        default=False,
        help="Enable debug logging and save failure artifacts to state_dir",
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
    sub.add_parser("web", help="Start web UI")

    args = parser.parse_args()

    # --debug can appear before or after the subcommand; merge both
    debug = getattr(args, "debug", False)
    _configure_logging(debug)

    if args.command == "scrape":
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
        print("web: not yet implemented")
        sys.exit(0)
    else:
        parser.print_help()
        sys.exit(0)


if __name__ == "__main__":
    main()