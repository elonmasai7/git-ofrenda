# git-ofrenda 🏵️💀🕯️

**An ofrenda for the files your repo has lost.**

Every codebase has ghosts: the FTP uploader nobody remembers, the IE8 shim, the roadmap that was a lie.
`git-ofrenda` digs them out of your git history, reads what they contained when they died, and has a
**model running on your own machine** write each one a *calavera literaria*, the playful epitaph verse
from Día de los Muertos tradition. Then you can hold a **séance** in your browser and talk to them.

![The ofrenda](docs/screenshots/01-ofrenda.png)

> **About the screenshots.** They were captured from the real tool, but on a machine with no model installed,
> so they show the built-in template mode (each card is labelled `verse: template`, and the page header says
> "no model was used"). With a model running, verses and séance replies are written by the model from each
> file's actual code, and the header says so (e.g. "Verses written by gemma3, a model running on this machine").

## Why open models?

Deleted code is often the code you would least like to paste into someone else's API: proprietary,
embarrassing, or full of credentials someone forgot to rotate.

- **Private by construction.** Source goes from `git` to a model on your own machine, and nowhere else.
- **Works offline.** On a plane, in an air-gapped office, with the Wi-Fi off.
- **Swappable.** Any model your server can run: Gemma, Llama, Qwen, Mistral, or your own fine-tune.
- **Free and durable.** No per-token cost, no key to expire, no service that can disappear.
- **Zero runtime dependencies.** Python 3.9+ standard library and `git`.
- **Never blocked on the model.** If it is off, slow, or answers badly, everything degrades to
  fact-based templates and says so on the page.

## Install

```bash
pip install .            # from a clone; installs the `git-ofrenda` command
# or run without installing:
python -m pip install -e . && python -m git_ofrenda --help
```

`git ofrenda ...` also works, because git runs any `git-ofrenda` on your PATH.

## Quick start

```bash
# 1. a local model (Ollama shown; see "Model setup" for llama.cpp / LM Studio)
ollama pull gemma3

# 2. check everything is wired up
git-ofrenda doctor

# 3. honor the 6 most-loved dead files in the current repo
git-ofrenda build

# 4. or talk to them
git-ofrenda seance
```

Want to try it first? Build a repo full of ghosts:

```bash
python examples/make_demo_repo.py /tmp/demo-repo
git-ofrenda scan /tmp/demo-repo
git-ofrenda seance /tmp/demo-repo
```

![Terminal session](docs/screenshots/06-terminal.png)

## Commands

| Command | What it does |
|---|---|
| `scan [repo]` | List dead files with lifespan, commits and cause of death. No model needed. `--json` for scripts. |
| `build [repo]` | Write the ofrenda as HTML (default), Markdown or JSON. `git-ofrenda [repo]` is shorthand for `build`. |
| `seance [repo]` | Serve a local page where you can chat with each ghost. |
| `exhume REPO DEST` | Restore the dead files' exact final contents into a folder. |
| `doctor` | Check git and your model server, and tell you what to fix. |

Selection flags (all commands except `doctor`): `-n/--limit`, `--include GLOB`, `--exclude GLOB`
(repeatable), `--since "1 year ago"`. Model flags (`build`, `seance`): `--backend`, `--model`, `--host`,
`--lang en|es`, `--no-cache`, `--refresh`. Run `git-ofrenda <command> --help` for details.

```bash
git-ofrenda build --since 2023-01-01 --exclude "docs/*" -n 10 -o ofrenda.html
git-ofrenda build -o ofrenda.md            # Markdown, great for a wiki or README
git-ofrenda build -o - --format json       # JSON to stdout
git-ofrenda exhume . ./grave --include "*.py"
```

## What each ghost card shows

![A single ghost card](docs/screenshots/02-card.png)

| Field | Where it comes from |
|---|---|
| Name, born, died, lifespan | `git log --follow` for that path, so a file renamed during its life keeps its full age |
| Commits, loved by | commits and authors that touched it |
| Cause of death, taken by | the commit that deleted it |
| Last words + calavera | the model, reading the file's final contents; otherwise a template using real function names, imports and docstrings |
| `verse:` badge | who wrote the verse: the model's name, or `template` |
| Final lines | the last lines the file held before it was deleted |

Ghosts are ranked by how loved they were (commits weighted with lifespan). Files that were only renamed
are not ghosts. Binary files, empty files and files over 2 MB are skipped.

## Séance

`git-ofrenda seance` serves the page on `127.0.0.1` and opens it. Press **Hold a séance** on any card and
ask it anything: why it died, who wrote it, what it did. Answers stream in as the model writes them, and
the model is told to stay truthful to the file's real contents and history. Conversations are saved per
repository, so they are still there next time; each card has a "forget this conversation" button.

![Talking to a ghost](docs/screenshots/03-seance.png)

If the model is unreachable, the ghost answers from git facts (shown in italics) instead of failing.

## Languages

`--lang es` writes the page, the verses and the séance in Spanish.

![Spanish ofrenda](docs/screenshots/04-espanol.png)

The page is responsive and self-contained (one HTML file you can send to a teammate):

<img src="docs/screenshots/05-mobile.png" alt="Mobile view" width="280">

## Model setup

| Server | Command | Flags |
|---|---|---|
| **Ollama** (default) | `ollama pull gemma3` | `--backend ollama --model gemma3` |
| **llama.cpp** | `llama-server -m model.gguf --port 8080` | `--backend openai --host http://localhost:8080` |
| **LM Studio** | start its local server | `--backend openai --host http://localhost:1234` |
| **vLLM / LocalAI / any OpenAI-compatible** | start the server | `--backend openai --host URL --model NAME` |
| **No model** | n/a | `--backend none` |

Everything can also be set with environment variables: `OFRENDA_BACKEND`, `OFRENDA_MODEL`,
`OFRENDA_HOST`, `OFRENDA_API_KEY` (only if your server wants one), and `OFRENDA_CACHE` (cache folder,
default `~/.cache/git-ofrenda`).

Verses are cached by (model, language, file, deleting commit), so re-running is instant and free.
Use `--refresh` to rewrite them. Small models sometimes ignore the requested format; git-ofrenda retries
once, then falls back to a template for that ghost.

## Privacy and security

- Your code only goes to the model server you point it at (by default `localhost`). There is no telemetry
  and no network access beyond that.
- The séance server binds to `127.0.0.1` only, rejects requests whose `Host` header is not localhost
  (DNS-rebinding defence), requires a custom `X-Ofrenda` header on POSTs (CSRF defence), and caps request
  sizes. It sends a Content-Security-Policy that limits the page to inline assets and same-origin requests.
- Everything a model or a repository can influence (file names, commit messages, author names, verses,
  séance history) is HTML-escaped. A file named `<script>...` cannot inject into the page.

## How it works

1. `git log --diff-filter=D -M` finds files deleted from history (renames are not deletions).
2. For each, `git log --follow` gives birth date, commits and authors; `git show <commit>^:path` recovers
   the last contents. In big repositories, candidates are pre-ranked in a single pass over history.
3. Verses come from the model (with a cached, retried, strictly parsed prompt) or from templates.
4. The result is rendered to HTML/Markdown/JSON, or served live with streaming chat.

More detail in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Project layout

```
src/git_ofrenda/   gitscan  facts  llm  prompts  poet  cache  render  server  cli  static/
tests/             44 tests; fake Ollama / OpenAI-compatible servers in tests/fakes.py
examples/          make_demo_repo.py
docs/              ARCHITECTURE.md, screenshots/
Dockerfile  .github/workflows/ci.yml  pyproject.toml  CHANGELOG.md  CONTRIBUTING.md
```

## Development

```bash
pip install -e .
python -m unittest discover -s tests -v
```

The tests build a real git repository with renames, binaries and deletions, and run the actual HTTP and
streaming code against fake Ollama and OpenAI-compatible servers, including model-down and
malformed-output cases. They cover scanning, ranking, parsing, caching, rendering and escaping, the
server's security checks and streaming, and every CLI command.

## Docker

```bash
docker build -t git-ofrenda .
docker run --rm -v "$PWD":/repo -v ofrenda-cache:/cache \
  -e OFRENDA_HOST=http://host.docker.internal:11434 git-ofrenda build -o /repo/ofrenda.html
```

The container is for `scan`, `build` and `exhume`; run `seance` natively, since it binds to localhost
by design.

## Known limits

- Detection depends on git's rename detection; a heavily rewritten rename can look like a death plus a birth.
- Files over 2 MB, binaries and empty files are skipped; only the first ~2,500 characters of a file go to the model.
- Template verses are only as specific as the facts regexes can find (function names, imports, docstring or comment).
- Model quality varies with model size; small models write plainer verses and sometimes ignore the format.

## License

MIT. Happy Día de los Muertos. 🕯️
