# XCrap Python SDK examples

Small, runnable projects built on [`xcrap-sdk`](https://pypi.org/project/xcrap-sdk/)
(installed as `xcrap-sdk`, imported as `xcrap`). XCrap needs no API key, so each one
works as soon as you install it.

| Example | What it does | Extra dependency |
| --- | --- | --- |
| [`cli/`](cli/) | `xcrap-cli tweet`, `thread`, `user`, `search` and `history` from your terminal, saving to CSV, Markdown or JSON | none (`argparse`) |
| [`discord-bot/`](discord-bot/) | Turns X links into clean embeds and sends `!thread` as a Markdown file | `discord.py` 2.x |
| [`telegram-bot/`](telegram-bot/) | `/tweet`, `/thread` and automatic link expansion | `python-telegram-bot` v21 |
| [`thread-archiver/`](thread-archiver/) | Saves a list of threads to `archive/<handle>-<id>.md`, waiting out rate limits | none |
| [`ai-summary/`](ai-summary/) | Builds a ready-to-send summary prompt from a thread, for any LLM | none |

## Running one

```bash
cd cli                      # or any other folder
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python xcrap_cli.py tweet https://x.com/jack/status/20
```

All examples need Python 3.9 or newer. The bots use the async client
(`AsyncXcrap`); the scripts use the sync one (`Xcrap`).

## Good to know

- Every example handles the SDK's errors: `XcrapNotFound` (deleted or private),
  `XcrapRateLimited` (wait `retry_after` seconds), `XcrapOptedOut` and
  `XcrapConnectionError`.
- Budgets are per endpoint, per IP. The full table is at <https://xcrap.cc/docs>.
- Bot tokens and AI keys are read from environment variables only. Copy
  `.env.example` to `.env`, fill it in and load it (for example
  `set -a; source .env; set +a`); never commit `.env`.
