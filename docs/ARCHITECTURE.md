# Architecture

![Architecture](architecture.png)

Data flows one way: git history becomes `Ghost` objects, `poet` gives them a voice, and `render` or
`server` presents them. The model server is optional and only ever sits behind `poet` and `server`.

## Modules

| Module | Role |
|---|---|
| `gitscan.py` | Finds deleted files, follows renames, reads final contents. `Ghost` is the central dataclass. |
| `facts.py` | Pulls function names, imports and a header comment out of source text with regexes. |
| `llm.py` | `Backend` interface; Ollama and OpenAI-compatible implementations; `none`. |
| `prompts.py` | Prompt text and strict parsing of the model's reply. |
| `poet.py` | Verse pipeline (cache, model, retry, template) and the rule-based séance fallback. |
| `cache.py` | Atomic, thread-safe JSON stores for verses and conversations. |
| `render.py` | HTML, Markdown and JSON output. Static assets live in `static/`. |
| `server.py` | Localhost séance server with NDJSON streaming and server-side history. |
| `cli.py` | `scan`, `build`, `seance`, `exhume`, `doctor`. |

## Decisions worth knowing about

**The model is optional everywhere.** Any model failure (unreachable, wrong model, bad output) falls back
to templates for that ghost. Every ghost records its `voice` (`template` or `model:<name>`), and the page
header counts how many verses each produced, so output cannot be mistaken for something it is not.

**Chat history lives on the server.** The browser sends only the new message. The server owns history,
caps it, and rebuilds the prompt from the ghost's facts each turn.

**Streaming is newline-delimited JSON over a plain HTTP/1.0 response.** The stream ends when the
connection closes, which avoids chunked-encoding handling in a standard-library server.

**Rename handling.** `--diff-filter=D -M` excludes renames from the set of deletions, and
`git log --follow` stitches a file's history across renames for its lifespan and author list.

**Scale.** With many deleted files, one pass over `git log --name-only` counts touches per path and only
the most-touched candidates get the per-file `git log`/`git show` calls.

## Adding things

- A backend: subclass `llm.Backend` (`generate`, `chat_stream`, `check`) and register it in `make_backend`.
- A language: add strings to `render.STRINGS`, templates and fallback answers to `poet.py`, and a name to
  `prompts.LANG_NAMES`.
