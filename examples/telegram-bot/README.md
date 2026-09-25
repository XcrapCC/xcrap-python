# Telegram bot (Python, python-telegram-bot v21)

- `/tweet <link>` replies with the post's text and stats.
- `/thread <link>` sends the whole thread as a `.md` document.
- Any message containing an X post link is expanded automatically.

## Setup

1. Talk to [@BotFather](https://t.me/BotFather), run `/newbot`, and copy the token.
2. To use it in groups, run `/setprivacy` in BotFather and choose *Disable*, so
   the bot can see plain links.
3. Install and configure:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # then paste your token into .env
```

| Variable | Required | Meaning |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | yes | The token from BotFather |

## Run

```bash
set -a; source .env; set +a
python bot.py
```

## Example

```text
You: /tweet https://x.com/NASA/status/2099558640319373599

Bot: NASA (@NASA)

     Welcome to the Artemis Accords, Djibouti 🇩🇯

     Djibouti has joined 71 other nations that have committed to a safe and
     peaceful exploration of space: https://t.co/j2FSgNO9LW

     1,586 likes · 172 reposts · 90 replies · 618,666 views
     1 attachment(s): https://pbs.twimg.com/media/HSMhdNKWIAAW4sk.jpg?name=orig
     https://x.com/NASA/status/2099558640319373599

You: /thread https://x.com/jack/status/20
Bot: [thread-20.md] Here is the whole thread.
```

Messages are sent as plain text, so nothing inside a post can break the formatting.
Errors come back as friendly replies, for example
"That post is deleted, private, or never existed."
