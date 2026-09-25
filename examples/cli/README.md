# xcrap-cli (Python)

Read public X posts, threads, profiles and searches from your terminal, and export
an account's history to CSV, Markdown or JSON. Built with `argparse`, nothing else.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

No keys or environment variables are needed.

## Usage

```bash
python xcrap_cli.py tweet https://x.com/jack/status/20
python xcrap_cli.py thread https://x.com/jack/status/20 --max 50
python xcrap_cli.py user jack --json
python xcrap_cli.py search "from:nasa moon" --feed top --since 2026-01-01
python xcrap_cli.py history nasa --max 200 --since 2026-01-01 --out nasa.csv
python xcrap_cli.py history --help
```

| Flag | Works with | Meaning |
| --- | --- | --- |
| `--json` | all | Print JSON instead of Markdown |
| `--max N` | `thread`, `history` | Posts to fetch (thread 1–100, history 1–1000) |
| `--since`, `--until` | `search`, `history` | Date window, e.g. `2026-01-01` |
| `--feed` | `search` | `latest`, `top`, `photos` or `videos` |
| `--replies` | `history` | Include replies to other accounts |
| `--out FILE` | `history` | Save to `.csv`, `.md` or `.json` (format follows the extension) |

Exit codes: `0` success, `1` the API said no (not found, rate limited...), `2` bad usage.

## Example output

```text
$ python xcrap_cli.py tweet https://x.com/jack/status/20
# jack (@jack)

**2006-03-21 20:50 UTC** · [permalink](https://x.com/jack/status/20)

just setting up my twttr

308,160 likes · 124,652 reposts · 18,016 replies · 7,149 quotes · 21,381 bookmarks

$ python xcrap_cli.py history nasa --max 10 --since 2026-01-01 --out nasa.csv
Saved to nasa.csv

$ head -1 nasa.csv
position,id,url,created_at,author_handle,author_name,author_followers,text,lang,likes,retweets,replies,quotes,bookmarks,views,media_count,media_types,media_urls,is_quote,quoted_url,possibly_sensitive

$ python xcrap_cli.py tweet https://x.com/jack/status/1111111111111111111
Not found: the post or account is deleted, private, suspended or never existed.
```

If you hit a rate limit, the tool tells you how long to wait:
`Slow down a little: try again in 42 seconds.`
