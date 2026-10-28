# Changelog

## 1.0.0
- `scan`, `build`, `seance`, `exhume` and `doctor` commands.
- Backends: Ollama, any OpenAI-compatible server (llama.cpp, LM Studio, vLLM), or none.
- Verse cache so reruns are instant; per-repo persistent séance conversations.
- Streaming séance chat in the browser; localhost-only server with Host and CSRF checks.
- English and Spanish (`--lang es`).
- Renames are followed, so a renamed file's life before the rename counts.
- HTML, Markdown and JSON output.
- Scales to large histories by pre-ranking deleted files in a single pass.
