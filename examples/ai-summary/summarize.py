"""Fetch a thread as Markdown and wrap it in a ready-to-send LLM prompt."""

from __future__ import annotations

import sys

from xcrap import Xcrap, XcrapConnectionError, XcrapError, XcrapNotFound, XcrapOptedOut, XcrapRateLimited

INSTRUCTIONS = """\
You are a careful editor. Summarise the X thread below for someone who has not read it.
Give: a one-sentence summary, 3 to 5 key points as bullets, and any links or numbers worth keeping.
Only use what is in the thread. Quote the author when wording matters."""


def build_prompt(thread_markdown: str) -> str:
    return f"{INSTRUCTIONS}\n\n<thread>\n{thread_markdown.strip()}\n</thread>"


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python summarize.py <x.com status link>", file=sys.stderr)
        return 2

    try:
        with Xcrap() as xcrap:
            markdown = xcrap.thread(sys.argv[1], markdown=True, max_tweets=100)
            tokens = xcrap.last_meta.markdown_tokens if xcrap.last_meta else None
    except XcrapNotFound:
        print("That post is deleted, private, or never existed.", file=sys.stderr)
        return 1
    except XcrapOptedOut:
        print("This account opted out of XCrap.", file=sys.stderr)
        return 1
    except XcrapRateLimited as error:
        print(f"Rate limited. Try again in {error.retry_after} seconds.", file=sys.stderr)
        return 1
    except XcrapConnectionError:
        print("Could not reach XCrap. Check your connection.", file=sys.stderr)
        return 1
    except XcrapError as error:
        print(f"Could not fetch the thread ({error.status}). Please retry in a minute.", file=sys.stderr)
        return 1

    prompt = build_prompt(markdown)
    note = f" (thread is about {tokens} tokens)" if tokens else ""
    print(f"Prompt ready{note}.\n", file=sys.stderr)
    print(prompt)

    # ── Send it to a model ──────────────────────────────────────────────────
    # Uncomment ONE of the blocks below. Keys come from environment variables only.
    # httpx is already installed with xcrap-sdk, so no extra package is needed.
    #
    # import os, httpx
    #
    # OpenAI-compatible endpoint (OpenAI, OpenRouter, Groq, ...):
    #
    # base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    # res = httpx.post(
    #     f"{base}/chat/completions",
    #     headers={"authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
    #     json={"model": os.environ["AI_MODEL"], "messages": [{"role": "user", "content": prompt}]},
    #     timeout=120,
    # )
    # print("\n--- Summary ---\n" + res.json()["choices"][0]["message"]["content"])
    #
    # Anthropic Messages API:
    #
    # res = httpx.post(
    #     "https://api.anthropic.com/v1/messages",
    #     headers={"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"},
    #     json={
    #         "model": os.environ["AI_MODEL"],
    #         "max_tokens": 1024,
    #         "messages": [{"role": "user", "content": prompt}],
    #     },
    #     timeout=120,
    # )
    # print("\n--- Summary ---\n" + res.json()["content"][0]["text"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
