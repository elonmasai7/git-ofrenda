# Architecture

```
git history ──► gitscan ──► Ghost ──► poet ──► Ghost(+verse) ──► render ──► .html / .md / .json
                              │         │                           │
                              │         ├─ llm (Ollama / OpenAI-compat / none)
                              │         └─ cache (verses.json)      └─► server (séance) ──► llm.chat_stream
                              └─ facts (functions, deps, intent)             └─ cache (seances/<repo>.json)
```

| Module | Responsibility |
|---|---|
| `gitscan` | Find files deleted from history (`git log --diff-filter=D -M`), follow renames for lifespan, recover final contents. Pre-ranks in one pass when there are many. |
| `facts` | Regex facts from source: function names, imports, docstring/comment intent. Used by templates and fallbacks. |
| `llm` | `Backend` interface and implementations. Streaming for chat; plain generation for verses. |
| `prompts` | Prompt text and strict parsing of the model's reply. |
| `poet` | Orchestrates verse writing: cache → model (retry once) → template. Also the rule-based séance fallback. |
| `cache` | Atomic, thread-safe JSON stores. |
| `render` | HTML (self-contained), Markdown, JSON. All text is escaped. |
| `server` | Localhost séance server: NDJSON streaming, server-side history, Host/CSRF checks. |
| `cli` | `scan`, `build`, `seance`, `exhume`, `doctor`. |

## Failure policy
A model is optional everywhere. If it is unreachable, malformed, or slow, each feature degrades to
facts-based templates and the page says so ("verse: template"). The tool never refuses to work.

## Provenance
Every verse records its `voice` (`template` or `model:<name>`); the page header counts how many were
model-written, so a screenshot can never silently pass off template text as model output.
