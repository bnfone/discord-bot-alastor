# Repository Guidelines

## Project Structure & Module Organization
- `src/bot.py`: Entrypoint (`python -m src.bot`). Sets intents, loads cogs.
- `src/commands/`: Discord cogs and slash commands (`radio.py`, `info.py`, `donate.py`). Add new cogs as `snake_case.py`.
- `src/config.py`: YAML config loader with ENV overrides.
- `config.yaml`: Default stations and bot settings. Mount or edit for local runs.
- Docker: `Dockerfile`, `docker-compose.yml`. CI: `.github/workflows/publish-docker.yml`.
- Assets: `alastor.jpg`. Tests (if added): `tests/` with `test_*.py`.

## Build, Test, and Development Commands
- Create venv and install:
  ```bash
  python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
  ```
- Run locally:
  ```bash
  export DISCORD_TOKEN=... \
         CONFIG_PATH=./config.yaml
  python -m src.bot
  ```
- Docker build/run:
  ```bash
  docker build -t alastor .
  docker compose up -d
  docker compose logs -f
  ```
- Tests (recommended):
  ```bash
  pytest -q
  ```

## Coding Style & Naming Conventions
- Python 3.10+, 4-space indentation, PEP 8.
- Names: modules/files `snake_case.py`; classes `PascalCase`; functions/vars `snake_case`.
- Strings and embeds in English; user-facing copy concise.
- Optional tooling: format/lint with `black` and `ruff` before PRs.

## Testing Guidelines
- Framework: `pytest`; place tests in `tests/` named `test_*.py`.
- Focus areas: command handlers in `src/commands/*`, config parsing in `src/config.py`.
- Mock Discord interactions; mock HTTP in `radio.resolve_stream_url`.
- Run with `pytest -q`. No strict coverage target; cover core logic paths.

## Commit & Pull Request Guidelines
- Commits: imperative, present tense; keep scoped (e.g., "add radio list view"). Conventional Commits (`feat:`, `fix:`, `chore:`) welcome.
- PRs: include clear description, rationale, logs/screenshots when relevant; link issues; note config/env changes (`DISCORD_TOKEN`, `CONFIG_PATH`, `BOT_PREFIX`). Keep changes focused and small.

## Security & Configuration Tips
- Required: set `DISCORD_TOKEN` (never commit tokens). Optional: `CONFIG_PATH`, `BOT_PREFIX`, `BOT_DESCRIPTION`.
- FFmpeg must be available (installed in Docker image). Locally, install via OS package manager.
- Validate radio URLs; prefer HTTPS. Avoid mounting writable secrets; use Docker/CI secrets.
