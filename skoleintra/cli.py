import argparse

def main():
    parser = argparse.ArgumentParser(prog="skoleintra")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("scrape", help="Run scraper once")
    sub.add_parser("web", help="Start web UI")
    args = parser.parse_args()

    if args.command == "scrape":
        print("scrape: not yet implemented")
    elif args.command == "web":
        print("web: not yet implemented")
    else:
        parser.print_help()

if __name__ == "__main__":
    main()