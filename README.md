# Voice-to-PDF Telegram Bot

> A Telegram bot for construction equipment rental companies. Users send voice messages in Russian — the bot transcribes them, extracts structured business data, and generates a professionally formatted PDF rental request form (заявка на аренду).

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://docs.astral.sh/ruff/)
[![Type checked: mypy](https://img.shields.io/badge/type%20checked-mypy-blue.svg)](https://mypy-lang.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

---

## Table of Contents

- [What It Does](#what-it-does)
- [How It Works](#how-it-works)
- [Prerequisites](#prerequisites)
- [Local Development Setup](#local-development-setup)
- [Configuration Reference](#configuration-reference)
- [Testing](#testing)
- [Linting & Type Checking](#linting--type-checking)
- [Docker](#docker)
- [Google Cloud Deployment](#google-cloud-deployment)
- [Project Structure](#project-structure)
- [Troubleshooting](#troubleshooting)
- [Documentation](#documentation)

---

## What It Does

A manager at a construction equipment rental company receives calls from clients requesting machinery. Instead of manually filling out forms, the manager sends a **voice message** to the Telegram bot describing the rental request in Russian. The bot:

1. **Transcribes** the voice message using OpenAI Whisper (`whisper-1`, Russian language)
2. **Extracts** structured data (client name, phone, equipment list, dates, delivery address, etc.) using GPT-4o-mini with structured output
3. **Generates** a PDF rental request form (заявка на аренду) via WeasyPrint from a Jinja2 HTML template
4. **Sends** the PDF document back to the user in Telegram

**Who it's for**: Construction equipment rental companies that want to streamline intake of rental requests from voice calls into formatted PDF documents.

---

## How It Works

```
┌──────────────┐     voice message      ┌──────────────────┐
│  Telegram    │ ─────────────────────▶ │  Bot             │
│  User        │                        │  (aiogram 3.x)   │
└──────────────┘                        └──────┬───────────┘
                                               │
                                    1. Download .ogg voice file
                                    2. Send to OpenAI Whisper API (ru)
                                               │
                                               ▼
                                    ┌──────────────────┐
                                    │  OpenAI Whisper  │
                                    │  (STT, Russian)  │
                                    └────────┬─────────┘
                                             │ transcribed text
                                             ▼
                                    3. Send to GPT-4o-mini
                                       with structured output
                                             │
                                             ▼
                                    ┌──────────────────┐
                                    │  GPT-4o-mini     │
                                    │  (JSON schema)   │
                                    └────────┬─────────┘
                                             │ RentalRequestData (Pydantic)
                                             ▼
                                    4. Render HTML (Jinja2)
                                       → PDF (WeasyPrint)
                                             │
                                             ▼
                                    5. Send PDF back to user
                                               │
                                               ▼
┌──────────────┐     PDF document       ┌──────────────────┐
│  Telegram    │ ◀───────────────────── │  Bot             │
│  User        │                        │                  │
└──────────────┘                        └──────────────────┘
```

The bot runs in **polling mode** by default (for local development) or **webhook mode** in production (on Google Cloud Run).

---

## Prerequisites

- **Python 3.12+**
- **Telegram Bot Token** — create a bot via [@BotFather](https://t.me/BotFather) and get the token
- **OpenAI API key** — with access to Whisper and GPT-4o-mini
- **Your Telegram user ID** — find it via [@userinfobot](https://t.me/userinfobot) or similar
- **Google Cloud project** (production only) — for Cloud Run deployment

---

## Local Development Setup

1. **Clone the repository**:

   ```bash
   git clone https://github.com/YOUR_ORG/stt-demo.git
   cd stt-demo
   ```

2. **Create a virtual environment** (recommended):

   ```bash
   python -m venv .venv
   # Windows
   .venv\Scripts\activate
   # Linux/macOS
   source .venv/bin/activate
   ```

3. **Create `.env` from `.env.example`**:

   ```bash
   cp .env.example .env
   ```

4. **Fill in the required values** in `.env`:

   ```env
   TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
   OPENAI_API_KEY=sk-...
   ALLOWED_USER_IDS=123456789
   ```

   > `ALLOWED_USER_IDS` is a comma-separated whitelist of Telegram user IDs. Only these users can interact with the bot.

5. **Install the package with dev dependencies**:

   ```bash
   pip install -e ".[dev]"
   ```

6. **Run the bot** (polling mode by default):

   ```bash
   python -m voice_bot
   ```

   The bot will connect to Telegram via long polling and respond to voice messages from whitelisted users.

---

## Configuration Reference

All configuration is managed via environment variables (loaded from `.env` for local dev, or Secret Manager + env vars in production).

| Variable | Required | Default | Description |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Yes | — | Bot token from @BotFather |
| `OPENAI_API_KEY` | Yes | — | OpenAI API key |
| `ALLOWED_USER_IDS` | Yes | — | Comma-separated Telegram user IDs (whitelist) |
| `WEBHOOK_SECRET` | Yes (prod) | — | Secret token for webhook validation |
| `WEBHOOK_URL` | Yes (prod) | — | Public URL for webhook (Cloud Run URL) |
| `WEBHOOK_PATH` | No | `/webhook` | URL path for webhook endpoint |
| `USE_WEBHOOK` | No | `false` | `true` for production (webhook), `false` for local (polling) |
| `LOG_LEVEL` | No | `INFO` | Logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `PORT` | No | `8080` | Server port (set automatically by Cloud Run in production) |

See [`.env.example`](.env.example) for a template with inline comments.

---

## Testing

```bash
pytest -v
```

Tests cover:

- **Config** — settings loading from env vars, validation rules
- **Transcription** — Whisper API client (mocked via `respx`)
- **Extraction** — GPT-4o-mini structured output (mocked via `respx`)
- **Middleware** — access control whitelist logic
- **Handlers** — voice message processing flow, error responses (mocked services)

> **Note**: PDF generator tests (Step 22 in the plan) are skipped on Windows because WeasyPrint requires Pango/GTK native libraries. They run on Linux (e.g., in the Docker container) where these dependencies are available.

With coverage report:

```bash
pytest --cov=src/ --cov-report=term-missing
```

---

## Linting & Type Checking

```bash
ruff check . && ruff format --check . && mypy src/
```

- **ruff** — linting (rules: E, W, F, I, UP, B, SIM, ANN) + formatting (double quotes, line length 100)
- **mypy** — strict type checking (Python 3.12 target)

To auto-fix lint issues and format code:

```bash
ruff check --fix . && ruff format .
```

---

## Docker

Build the image:

```bash
docker build -t voice-bot .
```

Run locally (requires `.env` file or env vars):

```bash
docker run --rm --env-file .env -p 8080:8080 voice-bot
```

The Dockerfile uses a **multi-stage build**:

- **Builder stage**: `python:3.12-slim`, builds the wheel
- **Runtime stage**: `python:3.12-slim` + WeasyPrint system dependencies (Pango, Cairo, DejaVu fonts) + non-root `app` user

---

## Google Cloud Deployment

The bot is designed for **Google Cloud Run** with CI/CD via **Google Cloud Build**.

### Summary

1. Enable APIs: Cloud Run, Artifact Registry, Secret Manager, IAM, Cloud Build
2. Create secrets in Secret Manager: `telegram-bot-token`, `openai-api-key`, `allowed-user-ids`, `webhook-secret`
3. Create a Cloud Build trigger connected to your repository (watches `master` branch)
4. Push to `master` → Cloud Build runs `cloudbuild.yaml`, builds Docker image, pushes to Artifact Registry, deploys to Cloud Run

> **Full step-by-step guide**: see [docs/PLAN.md](docs/PLAN.md) → **Step 28** for the complete infrastructure setup guide with all `gcloud` commands.

### CI/CD Pipeline

The Cloud Build pipeline (`cloudbuild.yaml`) has three steps:

1. **Build** — builds the Docker image from the project's `Dockerfile`
2. **Push** — pushes the image to Artifact Registry
3. **Deploy** — deploys the image to Cloud Run with secrets from Secret Manager and `--no-allow-unauthenticated`

Tests (ruff, mypy, pytest) are not run in CI — run them locally with `pytest -v`, `ruff check .`, `mypy src/`.

---

## Project Structure

```
stt-demo/
├── pyproject.toml                 # Project config, dependencies, ruff/mypy settings
├── README.md                      # This file
├── .env.example                   # Template for environment variables
├── .gitignore
├── .dockerignore
│
├── docs/
│   ├── Overview.md                # Architecture, data flow, dependencies
│   └── PLAN.md                    # Step-by-step implementation plan
│
├── src/
│   └── voice_bot/
│       ├── __init__.py            # Package marker (version)
│       ├── __main__.py            # Entry point: python -m voice_bot
│       ├── config.py              # Pydantic Settings (env vars)
│       ├── bot.py                 # Bot + Dispatcher setup, webhook/polling lifecycle
│       ├── handlers.py            # Telegram handlers (voice, /start, /help, fallback)
│       ├── middleware.py          # Access control (user ID whitelist)
│       ├── models.py              # Pydantic models: RentalRequestData, EquipmentItem
│       ├── prompts.py             # System prompt for GPT-4o-mini extraction
│       ├── exceptions.py          # Custom exception hierarchy
│       ├── logging_config.py      # Structured JSON logging (structlog)
│       ├── services/
│       │   ├── transcription.py   # OpenAI Whisper API client (async)
│       │   ├── extraction.py      # GPT-4o-mini structured output client (async)
│       │   └── pdf_generator.py   # WeasyPrint PDF generation from Jinja2 template
│       ├── templates/
│       │   └── rental_request.html # Jinja2 HTML template for the PDF
│       └── static/
│           └── styles.css          # CSS for PDF (A4, Cyrillic fonts)
│
└── tests/
    ├── conftest.py                # Pytest fixtures
    ├── test_config.py             # Settings loading & validation
    ├── test_transcription.py      # Whisper API client tests
    ├── test_extraction.py         # GPT-4o-mini structured output tests
    ├── test_handlers.py           # Handler logic tests
    └── test_middleware.py         # Access control tests
```

---

## Troubleshooting

- **"У вас нет доступа к этому боту."** — Your Telegram user ID is not in `ALLOWED_USER_IDS`. Find your ID via [@userinfobot](https://t.me/userinfobot) and add it to `.env`.
- **Bot doesn't respond** — Check that `TELEGRAM_BOT_TOKEN` is correct and the bot is running. In polling mode, ensure no other instance is polling the same token.
- **OpenAI API errors** — Verify `OPENAI_API_KEY` is valid and has sufficient quota for Whisper and GPT-4o-mini.
- **PDF generation fails locally (Windows)** — WeasyPrint requires Pango/GTK native libraries. Use Docker (`docker build -t voice-bot .`) or WSL for local PDF testing.
- **Webhook not registering (production)** — Ensure `WEBHOOK_URL`, `WEBHOOK_PATH`, and `WEBHOOK_SECRET` are all set. Check startup logs for the webhook registration result.
- **Cloud Build trigger not firing** — Verify the trigger is connected to the correct branch (`^master$`) and repository in GCP Console. Ensure the Cloud Build GitHub app is authorized for your repository.

---

## Documentation

- **[docs/Overview.md](docs/Overview.md)** — Full architecture overview, data flow diagrams, dependency table, error handling strategy
- **[docs/PLAN.md](docs/PLAN.md)** — Step-by-step implementation plan (28 steps), including the complete Google Cloud infrastructure setup guide (Step 28)
