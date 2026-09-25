# Discord bot (Python, discord.py 2.x)

Watches your channels. When someone posts an x.com or twitter.com post link, the
bot replies with a clean embed: author and avatar, the text, likes, reposts and
replies, and the first image. `!thread <link>` sends the whole unrolled thread as
a Markdown file.

## Setup

1. Create an application at <https://discord.com/developers/applications>, add a
   bot, and copy its token.
2. On the **Bot** page, switch on **Message Content Intent**.
3. Invite the bot with the `bot` scope and the *Send Messages*, *Embed Links*,
   *Attach Files* and *Read Message History* permissions.
4. Install and configure:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # then paste your token into .env
```

| Variable | Required | Meaning |
| --- | --- | --- |
| `DISCORD_TOKEN` | yes | Your bot token |

## Run

```bash
set -a; source .env; set +a
python bot.py
```

## Example

A message containing `https://x.com/NASA/status/2099558640319373599` gets this embed:

```text
NASA (@NASA)
Welcome to the Artemis Accords, Djibouti 🇩🇯

Djibouti has joined 71 other nations that have committed to a safe and
peaceful exploration of space: https://t.co/j2FSgNO9LW

Likes 1,586    Reposts 172    Replies 90
[photo]
via xcrap.cc • 14/09/2026 17:59
```

`!thread https://x.com/jack/status/20` replies "Here is the whole thread:" with
`thread-20.md` attached.

The bot uses `AsyncXcrap`, so fetching a post never blocks other messages. It
expands at most three links per message, and if XCrap asks it to slow down it
says so in the channel ("Try again in 30s") instead of failing silently.
