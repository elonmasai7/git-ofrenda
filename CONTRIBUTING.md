# Contributing

    pip install -e .
    python -m unittest discover -s tests -v

- No runtime dependencies: keep it standard library only.
- Tests never need a real model: `tests/fakes.py` provides fake Ollama and OpenAI-compatible servers.
- Anything the model writes must be treated as untrusted text: it is always HTML-escaped on output.
- Adding a backend: subclass `llm.Backend` (`generate`, `chat_stream`, `check`) and register it in `make_backend`.
- Adding a language: add strings to `render.STRINGS`, templates to `poet.py`, and a name to `prompts.LANG_NAMES`.
