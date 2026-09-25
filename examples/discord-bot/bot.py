"""A Discord bot that expands X links into clean embeds and unrolls threads on request."""

from __future__ import annotations

import io
import os
import re
import sys
from datetime import datetime, timezone

import discord

from xcrap import AsyncXcrap, Tweet, XcrapConnectionError, XcrapNotFound, XcrapOptedOut, XcrapRateLimited

STATUS_LINK = re.compile(r"https?://(?:www\.|mobile\.)?(?:x|twitter)\.com/\w{1,15}/status/(\d+)", re.I)
MAX_LINKS_PER_MESSAGE = 3


def number(value: int | None) -> str:
    return "n/a" if value is None else f"{value:,}"


def explain(error: Exception) -> str:
    """Turn an SDK error into a short, friendly sentence for the channel."""
    if isinstance(error, XcrapNotFound):
        return "That post is deleted, private, or never existed."
    if isinstance(error, XcrapOptedOut):
        return "This account asked not to be shown through XCrap."
    if isinstance(error, XcrapRateLimited):
        return f"I am reading a lot of posts right now. Try again in {error.retry_after}s."
    if isinstance(error, XcrapConnectionError):
        return "I could not reach XCrap just now. Please try again soon."
    return "Something went wrong while reading that post. Please try again in a minute."


def build_embed(tweet: Tweet) -> discord.Embed:
    author = tweet.author
    embed = discord.Embed(description=(tweet.text or "*(no text)*")[:4000], url=tweet.url, colour=0x1D9BF0)
    if author:
        embed.set_author(name=f"{author.name} (@{author.screen_name})", url=author.url, icon_url=author.avatar_url)
    embed.add_field(name="Likes", value=number(tweet.metrics.likes))
    embed.add_field(name="Reposts", value=number(tweet.metrics.retweets))
    embed.add_field(name="Replies", value=number(tweet.metrics.replies))
    if tweet.created_timestamp:
        embed.timestamp = datetime.fromtimestamp(tweet.created_timestamp, tz=timezone.utc)
    photo = next((m.url for m in tweet.media if m.type == "photo"), None)
    image = photo or (tweet.media[0].thumbnail_url if tweet.media else None)
    if image:
        embed.set_image(url=image)
    embed.set_footer(text="via xcrap.cc")
    return embed


class XcrapBot(discord.Client):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True  # also switch this on in the Developer Portal
        super().__init__(intents=intents)
        self.xcrap: AsyncXcrap | None = None

    async def setup_hook(self) -> None:
        self.xcrap = AsyncXcrap()

    async def close(self) -> None:
        if self.xcrap:
            await self.xcrap.aclose()
        await super().close()

    async def on_ready(self) -> None:
        print(f"Logged in as {self.user}")

    async def send_thread(self, message: discord.Message, url: str | None) -> None:
        match = STATUS_LINK.search(url or "")
        if not match:
            await message.reply("Usage: `!thread <x.com status link>`")
            return
        async with message.channel.typing():
            try:
                markdown = await self.xcrap.thread(match.group(0), markdown=True, max_tweets=100)
            except Exception as error:  # noqa: BLE001 - every failure gets a friendly reply
                await message.reply(explain(error))
                return
        file = discord.File(io.BytesIO(markdown.encode("utf-8")), filename=f"thread-{match.group(1)}.md")
        await message.reply("Here is the whole thread:", file=file)

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        if message.content.startswith("!thread"):
            parts = message.content.split()
            await self.send_thread(message, parts[1] if len(parts) > 1 else None)
            return

        links = list(dict.fromkeys(m.group(0) for m in STATUS_LINK.finditer(message.content)))
        for link in links[:MAX_LINKS_PER_MESSAGE]:
            try:
                tweet = await self.xcrap.tweet(link)
                await message.reply(embed=build_embed(tweet), mention_author=False)
            except Exception as error:  # noqa: BLE001
                await message.reply(explain(error), mention_author=False)


if __name__ == "__main__":
    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        sys.exit("Set DISCORD_TOKEN to your bot token first (see .env.example).")
    XcrapBot().run(token)
