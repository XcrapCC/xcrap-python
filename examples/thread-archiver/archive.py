"""Save every thread from a list of X links as Markdown files in archive/."""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path
from typing import Callable, TypeVar

from xcrap import Xcrap, XcrapConnectionError, XcrapError, XcrapNotFound, XcrapOptedOut, XcrapRateLimited

MAX_ATTEMPTS = 5
STATUS_LINK = re.compile(r"(?:x|twitter)\.com/(\w{1,15})/status/(\d+)", re.I)
T = TypeVar("T")


def with_retry(task: Callable[[], T], label: str) -> T:
    """Run ``task``, waiting out rate limits and brief network trouble before retrying."""
    attempt = 1
    while True:
        try:
            return task()
        except (XcrapRateLimited, XcrapConnectionError) as error:
            if attempt >= MAX_ATTEMPTS:
                raise
            wait = (error.retry_after or 60) if isinstance(error, XcrapRateLimited) else 5 * attempt
            print(f"  {label}: waiting {wait}s before trying again...")
            time.sleep(wait)
            attempt += 1


def main() -> int:
    input_file = Path(sys.argv[1] if len(sys.argv) > 1 else "urls.txt")
    out_dir = Path(sys.argv[2] if len(sys.argv) > 2 else "archive")
    if not input_file.exists():
        print(f"{input_file} not found. Put one post link per line in it.")
        return 2

    lines = [line.strip() for line in input_file.read_text(encoding="utf-8").splitlines()]
    urls = [line for line in lines if line and not line.startswith("#")]
    out_dir.mkdir(parents=True, exist_ok=True)
    saved = skipped = failed = 0

    with Xcrap() as xcrap:
        for url in urls:
            match = STATUS_LINK.search(url)
            if not match:
                print(f"? {url} is not a post link, skipping")
                failed += 1
                continue
            handle, post_id = match.groups()
            target = out_dir / f"{handle}-{post_id}.md"
            if target.exists():
                print(f"= {target} already archived")
                skipped += 1
                continue

            try:
                markdown = with_retry(
                    lambda: xcrap.thread(url, markdown=True, max_tweets=100), f"{handle}/{post_id}"
                )
            except XcrapNotFound:
                print(f"x {url}: deleted, private or never existed")
                failed += 1
            except XcrapOptedOut:
                print(f"x {url}: the account opted out")
                failed += 1
            except XcrapError as error:
                print(f"x {url}: failed ({error.status or 'network error'}), try again later")
                failed += 1
            else:
                target.write_text(markdown, encoding="utf-8")
                print(f"+ {target}")
                saved += 1

    print(f"\nDone: {saved} saved, {skipped} already there, {failed} failed.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
