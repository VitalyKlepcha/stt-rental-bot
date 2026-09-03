# Voice-to-PDF Telegram Bot — Overview

A Telegram bot for a construction equipment rental company. Users send voice messages in Russian; the bot transcribes them via OpenAI Whisper, extracts structured business data via GPT-4o-mini, and generates a professionally formatted PDF rental request form (заявка на аренду).

## Architecture Diagram

```
┌──────────────┐     voice message      ┌──────────────────┐
│  Telegram    │ ─────────────────────▶ │  Cloud Run       │
│  User        │                        │  (aiogram 3.x    │
│              │                        │   webhook +      │
│              │                        │   aiohttp)       │
└──────────────┘                        └──────┬───────────┘
                                               │
                                    1. Download .ogg voice file
                                               │
                                    2. Send to OpenAI Whisper API
                                               │
                                               ▼
                                    ┌──────────────────┐
                                    │  OpenAI API      │
                                    │  whisper-1       │
                                    │  (STT, Russian)  │
                                    └────────┬─────────┘
                                             │ transcribed text
                                             ▼
                                    3. Send to GPT-4o-mini
                                       with structured output
                                             │
                                             ▼
                                    ┌──────────────────┐
                                    │  OpenAI API      │
                                    │  gpt-4o-mini     │
                                    │  (JSON schema)   │
                                    └────────┬─────────┘
                                             │ RentalRequestData (Pydantic)
                                             ▼
                                    4. Render HTML template
                                       (Jinja2) → PDF (WeasyPrint)
                                             │
                                             ▼
                                    5. Send PDF back to user
                                               │
                                               ▼
┌──────────────┐     PDF document       ┌──────────────────┐
│  Telegram    │ ◀───────────────────── │  Cloud Run       │
│  User        │                        │                  │
└──────────────┘                        └──────────────────┘

External Services:
  - Telegram Bot API (webhook mode)
  - OpenAI API (Whisper + GPT-4o-mini)

Google Cloud:
  - Cloud Run (containerized app)
  - Artifact Registry (Docker images)
  - Secret Manager (API keys, bot token)

CI/CD:
  - GitHub Actions → Workload Identity Federation → Cloud Run
```

## Project Structure

```
stt-demo/
├── pyproject.toml                 # Project config, dependencies, ruff/mypy settings
├── README.md                      # Setup, deployment, usage instructions
├── Dockerfile                     # Multi-stage build: python:3.12-slim + WeasyPrint deps
├── .dockerignore                  # Exclude .git, __pycache__, .venv, etc.
├── .env.example                   # Template for local development env vars
├── .gitignore                     # Python + IDE + env files
│
├── .github/
│   └── workflows/
│       └── deploy.yml             # CI/CD: lint → test → build → push to Artifact Registry → deploy to Cloud Run
│
├── docs/
│   ├── Overview.md                # This file — architecture, structure, reference
│   └── PLAN.md                    # Step-by-step implementation plan
│
├── src/
│   └── voice_bot/
│       ├── __init__.py            # Package marker
│       ├── __main__.py            # Entry point: python -m voice_bot
│       ├── config.py              # Pydantic Settings: loads from env / Secret Manager
│       ├── bot.py                 # Bot + Dispatcher setup, webhook/polling mode, lifecycle
│       ├── handlers.py            # Telegram message handlers (voice, /start, /help, fallback)
│       ├── middleware.py          # Access control middleware (user ID whitelist)
│       ├── models.py              # Pydantic models: RentalRequestData (LLM output schema)
│       ├── prompts.py             # System prompt for GPT-4o-mini entity extraction
│       ├── services/
│       │   ├── __init__.py
│       │   ├── transcription.py   # OpenAI Whisper API client (async)
│       │   ├── extraction.py      # GPT-4o-mini structured output client (async)
│       │   └── pdf_generator.py   # WeasyPrint PDF generation from Jinja2 HTML template
│       ├── templates/
│       │   └── rental_request.html # Jinja2 HTML template for the PDF
│       ├── static/
│       │   └── styles.css          # CSS for PDF (print media, Cyrillic fonts)
│       └── exceptions.py          # Custom exception classes
│
└── tests/
    ├── __init__.py
    ├── conftest.py                # Pytest fixtures: mock OpenAI, mock Telegram, sample data
    ├── test_config.py             # Settings loading from env vars
    ├── test_handlers.py           # Handler logic with mocked bot
    ├── test_transcription.py      # Whisper API client (mocked httpx)
    ├── test_extraction.py         # GPT-4o-mini structured output (mocked)
    ├── test_pdf_generator.py      # PDF generation from sample data (verify output)
    └── test_middleware.py         # Access control middleware
```

## Dependencies (pyproject.toml)

### Runtime Dependencies

| Package | Version | Justification |
|---|---|---|
| `aiogram` | >=3.13,<4.0 | Telegram bot framework. Async-native, webhook support, Pydantic types |
| `openai` | >=1.50,<2.0 | OpenAI Python SDK. AsyncOpenAI client, structured output parsing |
| `weasyprint` | >=62.0 | HTML/CSS → PDF. Cyrillic via Pango, Jinja2 templating, CSS Paged Media |
| `jinja2` | >=3.1 | HTML template engine for PDF generation |
| `pydantic` | >=2.0 | Data models, structured output schema for GPT-4o-mini |
| `pydantic-settings` | >=2.0 | Settings management from env vars / .env file |
| `aiohttp` | >=3.9 | Async HTTP server for webhook (aiogram dependency, also used directly) |
| `structlog` | >=24.0 | Structured JSON logging for Cloud Run |
| `python-dotenv` | >=1.0 | Load .env for local development |

### Dev Dependencies

| Package | Version | Justification |
|---|---|---|
| `ruff` | >=0.6 | Linter + formatter (replaces flake8, isort, black) |
| `mypy` | >=1.11 | Static type checking |
| `pytest` | >=8.0 | Test framework |
| `pytest-asyncio` | >=0.24 | Async test support |
| `pytest-cov` | >=5.0 | Coverage reporting |
| `respx` | >=0.21 | Mock httpx calls (OpenAI API) |

## Configuration Management

### Environment Variables

| Variable | Required | Description | Secret Manager? |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Yes | Bot token from @BotFather | Yes |
| `OPENAI_API_KEY` | Yes | OpenAI API key | Yes |
| `ALLOWED_USER_IDS` | Yes | Comma-separated Telegram user IDs (whitelist) | Yes |
| `WEBHOOK_SECRET` | Yes (prod) | Secret token for webhook validation | Yes |
| `WEBHOOK_URL` | Yes (prod) | Public URL for webhook (Cloud Run URL) | No (env var) |
| `WEBHOOK_PATH` | No | URL path for webhook (default: `/webhook`) | No |
| `USE_WEBHOOK` | No | `true` for prod, `false` for local (polling) | No |
| `LOG_LEVEL` | No | `INFO` (default), `DEBUG`, `WARNING`, `ERROR` | No |
| `PORT` | No | Server port (default: `8080`, set by Cloud Run) | No |

### Local Development

- `.env` file (gitignored) with all variables
- `USE_WEBHOOK=false` → bot uses long polling
- `python -m voice_bot` starts the bot

### Production (Cloud Run)

- Secrets mounted as env vars via Secret Manager
- `USE_WEBHOOK=true` → bot uses webhook mode
- Cloud Run injects `PORT` automatically
- Bot auto-registers webhook on startup via `bot.set_webhook()` in startup hook

## Data Flow — Step by Step

### 1. Voice Message Received

```
Telegram → POST /webhook (with X-Telegram-Bot-Api-Secret-Token)
         → aiohttp server
         → SimpleRequestHandler
         → Dispatcher
         → AccessControlMiddleware (check ALLOWED_USER_IDS)
         → handle_voice_message()
```

### 2. Transcription (Whisper API)

```python
async def transcribe(audio_bytes: bytes, filename: str) -> str:
    response = await openai_client.audio.transcriptions.create(
        file=(filename, audio_bytes),
        model="whisper-1",
        language="ru",
        response_format="text",
    )
    return response
```

### 3. Entity Extraction (GPT-4o-mini Structured Output)

```python
class RentalRequestData(BaseModel):
    client_name: str | None = None
    contact_phone: str | None = None
    equipment: list[EquipmentItem] = []
    rental_start_date: str | None = None
    rental_end_date: str | None = None
    rental_duration_days: int | None = None
    delivery_address: str | None = None
    preferred_delivery_time: str | None = None
    special_requirements: str | None = None
    urgency: Literal["normal", "urgent"] = "normal"

class EquipmentItem(BaseModel):
    name: str
    quantity: int = 1

async def extract_entities(transcript: str) -> RentalRequestData:
    completion = await openai_client.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": transcript},
        ],
        response_format=RentalRequestData,
        temperature=0,
    )
    return completion.choices[0].message.parsed
```

### 4. PDF Generation (WeasyPrint + Jinja2)

```python
def generate_pdf(data: RentalRequestData) -> bytes:
    template = jinja_env.get_template("rental_request.html")
    html = template.render(data=data, generated_at=datetime.now())
    doc = HTML(string=html, url_fetcher=...).render()
    pdf_bytes = doc.write_pdf()
    return pdf_bytes
```

### 5. Send PDF to User

```python
await bot.send_document(
    chat_id=chat_id,
    document=BufferedInputFile(pdf_bytes, filename="zayavka_na_arendu.pdf"),
    caption="Ваша заявка на аренду готова ✅",
)
```

## Error Handling Strategy

| Error Scenario | User Message | Logging |
|---|---|---|
| User not in whitelist | "У вас нет доступа к этому боту." | WARNING: unauthorized user {id} |
| Voice file download fails | "Не удалось получить голосовое сообщение. Попробуйте ещё раз." | ERROR: download failed |
| Whisper API error | "Ошибка при расшифровке голосового сообщения." | ERROR: whisper API error |
| Empty transcription | "Не удалось распознать речь в сообщении." | WARNING: empty transcript |
| GPT-4o-mini API error | "Ошибка при обработке данных." | ERROR: extraction API error |
| GPT-4o-mini returns None | "Не удалось извлечь данные из сообщения." | ERROR: parsed data is None |
| PDF generation fails | "Ошибка при создании PDF документа." | ERROR: weasyprint error |
| Unexpected exception | "Произошла непредвиденная ошибка. Попробуйте позже." | ERROR: unhandled exception with traceback |

All errors are caught in the handler with try/except, user gets a friendly Russian message, full error is logged as structured JSON.

## Testing Strategy

### Unit Tests

| Test File | What It Tests | Mocking |
|---|---|---|
| `test_config.py` | Settings load from env vars, validation | `monkeypatch` env vars |
| `test_transcription.py` | Whisper API call, response parsing, error handling | `respx` (mock httpx) |
| `test_extraction.py` | GPT-4o-mini structured output, Pydantic parsing, None handling | `respx` (mock httpx) |
| `test_pdf_generator.py` | PDF generation from sample data, output is valid PDF, contains expected text | No mock (WeasyPrint is local) |
| `test_handlers.py` | Handler routing, voice message processing flow, error responses | Mock services, mock bot |
| `test_middleware.py` | Whitelist check: allowed user passes, blocked user rejected | Mock update, mock bot |

### Integration Tests

- Full flow: voice message → transcription → extraction → PDF → send (all services mocked at HTTP level)
- Webhook endpoint: POST with valid/invalid secret token
- Health check endpoint: GET /healthz

### Test Data

- Sample Russian voice transcripts (text, not audio) for extraction tests
- Sample `RentalRequestData` objects for PDF generation tests
- Mock OpenAI API responses (JSON fixtures)

## Dockerfile

```dockerfile
# --- Builder stage ---
FROM python:3.12-slim AS builder

WORKDIR /build

COPY pyproject.toml ./
RUN pip install --no-cache-dir build && python -m build --wheel

# --- Runtime stage ---
FROM python:3.12-slim AS runtime

# WeasyPrint system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libpangoft2-1.0-0 \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    libffi8 \
    fontconfig \
    shared-mime-info \
    fonts-dejavu-core \
    && fc-cache -f \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd --create-home --shell /bin/bash app

WORKDIR /app

COPY --from=builder /build/dist/*.whl .
RUN pip install --no-cache-dir *.whl && rm *.whl

COPY src/ src/

RUN chown -R app:app /app
USER app

EXPOSE 8080

CMD ["python", "-m", "voice_bot"]
```

## GitHub Actions CI/CD Pipeline

```yaml
# .github/workflows/deploy.yml
name: deploy

on:
  push:
    branches: [main]

permissions:
  contents: read
  id-token: write  # Required for Workload Identity Federation

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -e ".[dev]"
      - run: ruff check .
      - run: ruff format --check .
      - run: mypy src/
      - run: pytest --cov=src/

  deploy:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - id: auth
        uses: google-github-actions/auth@v2
        with:
          workload_identity_provider: ${{ vars.WIF_PROVIDER }}
          service_account: ${{ vars.DEPLOY_SA }}
      - uses: google-github-actions/setup-gcloud@v2
      - name: Configure Docker
        run: gcloud auth configure-docker ${{ vars.REGION }}-docker.pkg.dev
      - name: Build and push
        run: |
          docker build -t ${{ vars.REGION }}-docker.pkg.dev/${{ vars.PROJECT_ID }}/voice-bot:${{ github.sha }} .
          docker push ${{ vars.REGION }}-docker.pkg.dev/${{ vars.PROJECT_ID }}/voice-bot:${{ github.sha }}
      - name: Deploy to Cloud Run
        uses: google-github-actions/deploy-cloudrun@v2
        with:
          service: voice-bot
          image: ${{ vars.REGION }}-docker.pkg.dev/${{ vars.PROJECT_ID }}/voice-bot:${{ github.sha }}
          region: ${{ vars.REGION }}
          flags: >-
            --set-secrets=TELEGRAM_BOT_TOKEN=telegram-bot-token:latest
            --set-secrets=OPENAI_API_KEY=openai-api-key:latest
            --set-secrets=ALLOWED_USER_IDS=allowed-user-ids:latest
            --set-secrets=WEBHOOK_SECRET=webhook-secret:latest
            --set-env-vars=USE_WEBHOOK=true
            --set-env-vars=WEBHOOK_URL=https://voice-bot-xxxx-uc.a.run.app
            --set-env-vars=WEBHOOK_PATH=/webhook
            --no-allow-unauthenticated
```
