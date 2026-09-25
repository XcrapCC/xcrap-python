# AI thread summary (Python)

Fetches a thread as Markdown (already compact and easy for a model to read) and
wraps it in a summary prompt. It prints the prompt, so you can paste it into any
chat app, pipe it to another tool, or send it to a model from the script.

It does not depend on any AI SDK. Two commented blocks at the bottom of
`summarize.py` show how to send the prompt to an OpenAI-compatible endpoint or to
Anthropic, using `httpx` (already installed with `xcrap-sdk`).

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

To send the prompt from the script, uncomment one block and set these (see
`.env.example`):

| Variable | When | Meaning |
| --- | --- | --- |
| `AI_MODEL` | either block | The model name your provider expects |
| `OPENAI_API_KEY` | OpenAI-compatible block | Your provider's key |
| `OPENAI_BASE_URL` | OpenAI-compatible block | Optional, defaults to `https://api.openai.com/v1` |
| `ANTHROPIC_API_KEY` | Anthropic block | Your Anthropic key |

XCrap itself needs no key.

## Run

```bash
python summarize.py https://x.com/jack/status/20
python summarize.py https://x.com/jack/status/20 > prompt.txt   # status line goes to stderr
```

## Example output

```text
Prompt ready (thread is about 57 tokens).

You are a careful editor. Summarise the X thread below for someone who has not read it.
Give: a one-sentence summary, 3 to 5 key points as bullets, and any links or numbers worth keeping.
Only use what is in the thread. Quote the author when wording matters.

<thread>
# Thread by jack (@jack)

1 post

---

### 1/1

**2006-03-21 20:50 UTC** · [permalink](https://x.com/jack/status/20)

just setting up my twttr

308,704 likes · 124,634 reposts · 18,017 replies · 7,158 quotes · 21,380 bookmarks
</thread>
```
