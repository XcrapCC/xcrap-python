#!/usr/bin/env python3
"""xcrap-cli: read public X posts, threads, profiles and searches from your terminal."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from xcrap import (
    Xcrap,
    XcrapBadRequest,
    XcrapConnectionError,
    XcrapError,
    XcrapNotFound,
    XcrapOptedOut,
    XcrapRateLimited,
)

FORMAT_BY_SUFFIX = {".csv": "csv", ".md": "markdown", ".json": "json"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="xcrap-cli",
        description="Read public X posts, threads, profiles and searches. Output is Markdown unless you pass --json.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    tweet = sub.add_parser("tweet", help="one post")
    tweet.add_argument("url")

    thread = sub.add_parser("thread", help="a whole thread, from any post in it")
    thread.add_argument("url")
    thread.add_argument("--max", type=int, default=25, help="posts to return, 1-100")

    user = sub.add_parser("user", help="a profile")
    user.add_argument("handle")

    search = sub.add_parser("search", help="search posts, with X's search operators")
    search.add_argument("query")
    search.add_argument("--feed", choices=["latest", "top", "photos", "videos"], default="latest")
    search.add_argument("--since", help="oldest date, e.g. 2026-01-01")
    search.add_argument("--until", help="newest date, e.g. 2026-02-01")

    history = sub.add_parser("history", help="up to 1,000 posts from one account")
    history.add_argument("handle")
    history.add_argument("--max", type=int, default=200, help="posts to fetch, 1-1000")
    history.add_argument("--since", help="oldest date, e.g. 2026-01-01")
    history.add_argument("--until", help="newest date, e.g. 2026-02-01")
    history.add_argument("--replies", action="store_true", help="include replies to other accounts")
    history.add_argument("--out", help="save to a .csv, .md or .json file")

    for command in (tweet, thread, user, search, history):
        command.add_argument("--json", action="store_true", help="print JSON instead of Markdown")
    return parser


def run(xcrap: Xcrap, args: argparse.Namespace, fmt: str):
    if args.command == "tweet":
        return xcrap.tweet(args.url, format=fmt)
    if args.command == "thread":
        return xcrap.thread(args.url, max_tweets=args.max, format=fmt)
    if args.command == "user":
        return xcrap.user(args.handle, format=fmt)
    if args.command == "search":
        return xcrap.search(args.query, feed=args.feed, since=args.since, until=args.until, format=fmt)
    return xcrap.user_history(
        args.handle,
        max_posts=args.max,
        since=args.since,
        until=args.until,
        include_replies=args.replies,
        format=fmt,
    )


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    out = getattr(args, "out", None)
    if out:
        fmt = FORMAT_BY_SUFFIX.get(Path(out).suffix.lower())
        if not fmt:
            parser.error("--out must end in .csv, .md or .json")
    else:
        fmt = "json" if args.json else "markdown"

    try:
        with Xcrap() as xcrap:
            result = run(xcrap, args, fmt)
    except XcrapNotFound:
        print("Not found: the post or account is deleted, private, suspended or never existed.", file=sys.stderr)
    except XcrapRateLimited as error:
        print(f"Slow down a little: try again in {error.retry_after} seconds.", file=sys.stderr)
    except XcrapOptedOut:
        print("This account asked not to be available through XCrap.", file=sys.stderr)
    except XcrapBadRequest:
        print("That did not look right: check the link, handle or dates and try again.", file=sys.stderr)
    except XcrapConnectionError:
        print("Could not reach XCrap. Check your internet connection and try again.", file=sys.stderr)
    except XcrapError as error:
        print(f"XCrap could not answer right now ({error.status}). Please retry in a minute.", file=sys.stderr)
    else:
        # JSON comes back as a model; its .raw field is the untouched API payload.
        text = result if isinstance(result, str) else json.dumps(result.raw, indent=2, ensure_ascii=False)
        if out:
            Path(out).write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
            print(f"Saved to {out}", file=sys.stderr)
        else:
            print(text)
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
