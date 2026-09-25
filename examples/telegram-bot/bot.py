"""A Telegram bot that reads X posts and threads for you (python-telegram-bot v21)."""

from __future__ import annotations

import os
import re
import sys

from telegram import LinkPreviewOptions, Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from xcrap import AsyncXcrap, Tweet, XcrapConnectionError, XcrapNotFound, XcrapOptedOut, XcrapRateLimited

STATUS_LINK = re.compile(r"https?://(?:www\.|mobile\.)?(?:x|twitter)\.com/\w{1,15}/status/(\d+)", re.I)
xcrap = AsyncXcrap()


def number(value: int | None) -> str:
    return "n/a" if value is None else f"{value:,}"


def explain(error: Exception) -> str:
    if isinstance(error, XcrapNotFound):
        return "That post is deleted, private, or never existed."
    if isinstance(error, XcrapOptedOut):
        return "This account asked not to be shown through XCrap."
    if isinstance(error, XcrapRateLimited):
        return f"Lots of requests right now. Please try again in {error.retry_after}s."
    if isinstance(error, XcrapConnectionError):
        return "Could not reach XCrap just now. Please try again soon."
    return "Something went wrong while reading that post. Please try again in a minute."


def describe(tweet: Tweet) -> str:
    """Plain text (no parse mode), so nothing in a post can break the formatting."""
    author = tweet.author
    m = tweet.metrics
    stats = f"{number(m.likes)} likes · {number(m.retweets)} reposts · {number(m.replies)} replies"
    if m.views:
        stats += f" · {number(m.views)} views"
    lines = [
        f"{author.name} (@{author.screen_name})" if author else "Unknown author",
        "",
        tweet.text or "(no text)",
        "",
        stats,
    ]
    if tweet.media:
        lines.append(f"{len(tweet.media)} attachment(s): {tweet.media[0].url}")
    lines.append(tweet.url or "")
    return "\n".join(lines)[:4096]


async def reply_with_tweet(update: Update, url: str) -> None:
    try:
        tweet = await xcrap.tweet(url)
        await update.message.reply_text(describe(tweet), link_preview_options=LinkPreviewOptions(is_disabled=True))
    except Exception as error:  # noqa: BLE001 - every failure gets a friendly reply
        await update.message.reply_text(explain(error))


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Send me an X link, or use /tweet <url> and /thread <url>.")


async def tweet_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /tweet https://x.com/user/status/123")
        return
    await reply_with_tweet(update, context.args[0])


async def thread_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    match = STATUS_LINK.search(context.args[0]) if context.args else None
    if not match:
        await update.message.reply_text("Usage: /thread https://x.com/user/status/123")
        return
    await update.message.chat.send_action(ChatAction.UPLOAD_DOCUMENT)
    try:
        markdown = await xcrap.thread(match.group(0), markdown=True, max_tweets=100)
    except Exception as error:  # noqa: BLE001
        await update.message.reply_text(explain(error))
        return
    await update.message.reply_document(
        document=markdown.encode("utf-8"),
        filename=f"thread-{match.group(1)}.md",
        caption="Here is the whole thread.",
    )


async def expand_links(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    links = list(dict.fromkeys(m.group(0) for m in STATUS_LINK.finditer(update.message.text)))
    for link in links[:3]:
        await reply_with_tweet(update, link)


async def shutdown(application: Application) -> None:
    await xcrap.aclose()


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        sys.exit("Set TELEGRAM_BOT_TOKEN to the token BotFather gave you (see .env.example).")
    app = Application.builder().token(token).post_shutdown(shutdown).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("tweet", tweet_command))
    app.add_handler(CommandHandler("thread", thread_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, expand_links))
    print("Bot is running. Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
