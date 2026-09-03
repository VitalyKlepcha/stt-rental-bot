# Implementation Plan — Voice-to-PDF Telegram Bot

> See `Overview.md` for architecture, project structure, dependencies, and reference material.
> This document defines the **step-by-step implementation plan** with dependencies and parallelism.

## Notation

- **Depends on**: steps that must be completed before this step can start
- **Parallel with**: steps that can be executed simultaneously with this step (if dependencies are met)
- **Files created**: the files this step produces
- **Verification**: how to confirm the step is done correctly

---

## Phase A — Project Scaffolding

### Step 1. Project configuration (`pyproject.toml`)

**Depends on**: nothing
**Parallel with**: nothing (everything depends on this)

Create `pyproject.toml` with:
- `[build-system]` — `setuptools` + `wheel` (or `hatchling`), Python 3.12+
- `[project]` — name, version, description, requires-python >=3.12
- `[project.dependencies]` — all runtime deps from Overview.md with exact version constraints
- `[project.optional-dependencies.dev]` — ruff, mypy, pytest, pytest-asyncio, pytest-cov, respx
- `[project.scripts]` — `voice-bot = "voice_bot.__main__:main"`
- `[tool.setuptools]` — package discovery: `src/` layout
- `[tool.ruff]` — line-length=100, target-version=py312, lint rules (E, W, F, I, UP, B, SIM, ANN)
- `[tool.ruff.format]` — quote-style = "double"
- `[tool.mypy]` — python_version=3.12, strict=true, warn_return_any=true, disallow_untyped_defs=true
- `[tool.pytest.ini_options]` — asyncio_mode=auto, testpaths=["tests"]

**Files created**: `pyproject.toml`
**Verification**: `pip install -e ".[dev]"` succeeds without errors

---

### Step 2. Git ignore + env template + docker ignore

**Depends on**: Step 1
**Parallel with**: Step 3, Step 4, Step 5, Step 6

Create three root-level config files:

**`.gitignore`**:
- Python: `__pycache__/`, `*.pyc`, `*.pyo`, `.venv/`, `venv/`, `*.egg-info/`, `dist/`, `build/`
- Env: `.env`
- IDE: `.idea/`, `.vscode/` (keep `.code-workspace`), `*.swp`
- OS: `.DS_Store`, `Thumbs.db`
- Test: `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `htmlcov/`, `.coverage`

**`.env.example`**:
- All env vars from Overview.md with placeholder values and inline comments
- `TELEGRAM_BOT_TOKEN=your_bot_token_here`
- `OPENAI_API_KEY=your_openai_api_key_here`
- `ALLOWED_USER_IDS=123456789,987654321`
- `WEBHOOK_SECRET=your_secret_token_here`
- `WEBHOOK_URL=https://your-cloud-run-url.a.run.app`
- `WEBHOOK_PATH=/webhook`
- `USE_WEBHOOK=false`
- `LOG_LEVEL=INFO`
- `PORT=8080`

**`.dockerignore`**:
- `.git/`, `.github/`, `docs/`, `tests/`, `.venv/`, `__pycache__/`, `.env`, `.mypy_cache/`, `.ruff_cache/`, `.pytest_cache/`, `*.md`

**Files created**: `.gitignore`, `.env.example`, `.dockerignore`
**Verification**: `git status` shows no unwanted files; `.env` is ignored

---

### Step 3. Package structure — `__init__.py` files

**Depends on**: Step 1
**Parallel with**: Step 2, Step 4, Step 5, Step 6

Create empty package marker files:
- `src/voice_bot/__init__.py` — with `__version__ = "0.1.0"`
- `src/voice_bot/services/__init__.py` — empty
- `tests/__init__.py` — empty

**Files created**: `src/voice_bot/__init__.py`, `src/voice_bot/services/__init__.py`, `tests/__init__.py`
**Verification**: `python -c "import voice_bot; print(voice_bot.__version__)"` prints `0.1.0`

---

## Phase B — Core Domain Modules (no external service calls)

### Step 4. Configuration (`config.py`)

**Depends on**: Step 1
**Parallel with**: Step 2, Step 3, Step 5, Step 6, Step 7

Create `src/voice_bot/config.py`:

- `Settings` class inheriting from `pydantic_settings.BaseSettings`
- `model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")`
- Fields (all from Overview.md env var table):
  - `telegram_bot_token: str` — required
  - `openai_api_key: str` — required
  - `allowed_user_ids: list[int]` — required, parsed from comma-separated env var
  - `webhook_secret: str | None = None` — required in webhook mode
  - `webhook_url: str | None = None` — required in webhook mode
  - `webhook_path: str = "/webhook"`
  - `use_webhook: bool = False`
  - `log_level: str = "INFO"`
  - `port: int = 8080`
- `Settings` model validator: if `use_webhook=True`, then `webhook_url` and `webhook_secret` must be set (raise `ValueError` with clear message)
- Module-level singleton: `settings = Settings()` (loaded once at import time)
- Use `@lru_cache` or simple module-level variable to avoid re-instantiation

**Files created**: `src/voice_bot/config.py`
**Verification**: Create a `.env` with test values, `python -c "from voice_bot.config import settings; print(settings.telegram_bot_token)"` prints the value

---

### Step 5. Domain models (`models.py`)

**Depends on**: Step 1
**Parallel with**: Step 2, Step 3, Step 4, Step 6, Step 7

Create `src/voice_bot/models.py`:

- `EquipmentItem(BaseModel)`:
  - `name: str` — equipment name (e.g. "Экскаватор JCB 3CX")
  - `quantity: int = Field(default=1, ge=1)` — quantity, minimum 1
- `RentalRequestData(BaseModel)`:
  - `client_name: str | None = None` — имя клиента
  - `contact_phone: str | None = None` — контактный телефон
  - `equipment: list[EquipmentItem] = Field(default_factory=list)` — список оборудования
  - `rental_start_date: str | None = None` — дата начала аренды (ISO format string, as transcribed)
  - `rental_end_date: str | None = None` — дата окончания аренды
  - `rental_duration_days: int | None = None` — длительность в днях
  - `delivery_address: str | None = None` — адрес доставки
  - `preferred_delivery_time: str | None = None` — предпочтительное время доставки
  - `special_requirements: str | None = None` — особые требования/примечания
  - `urgency: Literal["normal", "urgent"] = "normal"` — срочность
- All fields have `description` in Russian for the OpenAI structured output schema (the SDK uses Pydantic field descriptions as JSON schema descriptions for the LLM)
- `model_config = ConfigDict(extra="forbid")` — strict, no extra fields from LLM

**Files created**: `src/voice_bot/models.py`
**Verification**: `python -c "from voice_bot.models import RentalRequestData; print(RentalRequestData.model_json_schema())"` produces valid JSON schema

---

### Step 6. Custom exceptions (`exceptions.py`)

**Depends on**: Step 1
**Parallel with**: Step 2, Step 3, Step 4, Step 5, Step 7

Create `src/voice_bot/exceptions.py`:

- `VoiceBotError(Exception)` — base class for all domain errors
- `TranscriptionError(VoiceBotError)` — Whisper API failures (timeout, auth, invalid audio)
- `ExtractionError(VoiceBotError)` — GPT-4o-mini API failures (timeout, auth, parse error)
- `PDFGenerationError(VoiceBotError)` — WeasyPrint rendering failures
- `VoiceDownloadError(VoiceBotError)` — Telegram file download failures
- `AccessDeniedError(VoiceBotError)` — user not in whitelist
- Each exception accepts a message string and optional `cause: Exception | None`
- All exceptions include context in their string representation

**Files created**: `src/voice_bot/exceptions.py`
**Verification**: `python -c "from voice_bot.exceptions import TranscriptionError; raise TranscriptionError('test')"` raises with correct message

---

### Step 7. LLM prompts (`prompts.py`)

**Depends on**: Step 5 (references field names from `RentalRequestData`)
**Parallel with**: Step 2, Step 3, Step 4, Step 6

Create `src/voice_bot/prompts.py`:

- `SYSTEM_PROMPT: str` — the system prompt for GPT-4o-mini entity extraction
- Prompt content (in Russian):
  - Role: "Ты — ассистент, который извлекает структурированные данные из голосовых сообщений клиентов компании по аренде строительной техники."
  - Task: extract business entities from transcribed speech
  - Instructions:
    - Extract only information explicitly mentioned in the text
    - If a field is not mentioned, return `null` (not invented)
    - Equipment names should be specific (include brand/model if mentioned)
    - Dates should be in ISO format (YYYY-MM-DD) if possible, otherwise as spoken
    - Phone numbers in international format if possible
    - Urgency: "urgent" only if the client explicitly says it's urgent/срочно
    - Special requirements: any additional conditions, preferences, or notes
  - Examples: 2-3 short input→output examples in Russian (few-shot)
- The prompt is a module-level constant string, not loaded from file (it's code, not user-facing content)

**Files created**: `src/voice_bot/prompts.py`
**Verification**: `python -c "from voice_bot.prompts import SYSTEM_PROMPT; print(len(SYSTEM_PROMPT))"` prints a non-zero length

---

### Step 8. Structured logging setup (`logging_config.py`)

**Depends on**: Step 4 (uses `settings.log_level`)
**Parallel with**: Step 7, Step 9, Step 10, Step 11

Create `src/voice_bot/logging_config.py`:

- `setup_logging(level: str) -> None` function
- Uses `structlog` with:
  - `structlog.processors.TimeStamper(fmt="iso")` — ISO timestamps
  - `structlog.processors.JSONRenderer()` — JSON output for Cloud Run
  - `structlog.processors.add_log_level` — include level in output
- Configures standard library `logging` to route through structlog
- Sets log level from `settings.log_level`
- Called once at application startup (from `__main__.py` or `bot.py`)

**Files created**: `src/voice_bot/logging_config.py`
**Verification**: `python -c "from voice_bot.logging_config import setup_logging; setup_logging('DEBUG'); import structlog; log = structlog.get_logger(); log.info('test', key='value')"` prints JSON to stdout

---

## Phase C — Service Layer (external API clients)

### Step 9. Transcription service (`services/transcription.py`)

**Depends on**: Step 4 (config for API key), Step 6 (exceptions)
**Parallel with**: Step 7, Step 8, Step 10, Step 11

Create `src/voice_bot/services/transcription.py`:

- `TranscriptionService` class:
  - `__init__(self, api_key: str)` — stores key, creates `AsyncOpenAI` client lazily
  - `async def transcribe(self, audio_bytes: bytes, filename: str = "voice.ogg") -> str`:
    - Wraps audio bytes in `io.BytesIO` with filename
    - Calls `await self._client.audio.transcriptions.create(file=..., model="whisper-1", language="ru", response_format="text")`
    - Returns transcribed text string
    - Raises `TranscriptionError` on any `openai.OpenAIError` or network exception
    - Logs: request start (DEBUG), success (INFO with text length), failure (ERROR with exception)
  - `async def close(self) -> None` — closes the OpenAI client
- Module-level factory function: `def create_transcription_service() -> TranscriptionService` — uses `settings.openai_api_key`

**Files created**: `src/voice_bot/services/transcription.py`
**Verification**: Unit test with `respx` mocking the OpenAI API endpoint — see Step 20

---

### Step 10. Entity extraction service (`services/extraction.py`)

**Depends on**: Step 4 (config), Step 5 (models — `RentalRequestData`), Step 6 (exceptions), Step 7 (prompts)
**Parallel with**: Step 8, Step 9, Step 11

Create `src/voice_bot/services/extraction.py`:

- `ExtractionService` class:
  - `__init__(self, api_key: str)` — stores key, creates `AsyncOpenAI` client lazily
  - `async def extract(self, transcript: str) -> RentalRequestData`:
    - Calls `await self._client.chat.completions.parse(model="gpt-4o-mini", messages=[{system prompt}, {transcript}], response_format=RentalRequestData, temperature=0)`
    - Extracts `completion.choices[0].message.parsed`
    - If `parsed is None`: raises `ExtractionError("GPT-4o-mini returned no parsed data")`
    - Returns the `RentalRequestData` instance
    - Raises `ExtractionError` on any `openai.OpenAIError` or network exception
    - Logs: request start (DEBUG with transcript preview), success (INFO with extracted fields), failure (ERROR)
  - `async def close(self) -> None` — closes the OpenAI client
- Module-level factory: `def create_extraction_service() -> ExtractionService`

**Files created**: `src/voice_bot/services/extraction.py`
**Verification**: Unit test with `respx` mocking — see Step 21

---

### Step 11. PDF template — HTML (`templates/rental_request.html`)

**Depends on**: Step 5 (knows the data shape from `RentalRequestData`)
**Parallel with**: Step 8, Step 9, Step 10, Step 12

Create `src/voice_bot/templates/rental_request.html`:

- Jinja2 template that renders a professional rental request form (заявка на аренду)
- Document structure:
  - **Header**: "ЗАЯВКА НА АРЕНДУ СТРОИТЕЛЬНОЙ ТЕХНИКИ" — centered, bold, large font
  - **Date line**: "Дата заявки: {{ generated_at.strftime('%d.%m.%Y') }}" — right-aligned
  - **Section 1 — Клиент**:
    - Наименование клиента: `{{ data.client_name or "—" }}`
    - Контактный телефон: `{{ data.contact_phone or "—" }}`
  - **Section 2 — Оборудование**:
    - Table with columns: №, Наименование, Количество
    - Loop over `data.equipment` with `loop.index`
    - If empty: "—"
  - **Section 3 — Условия аренды**:
    - Дата начала: `{{ data.rental_start_date or "—" }}`
    - Дата окончания: `{{ data.rental_end_date or "—" }}`
    - Срок аренды (дней): `{{ data.rental_duration_days or "—" }}`
  - **Section 4 — Доставка**:
    - Адрес доставки: `{{ data.delivery_address or "—" }}`
    - Предпочтительное время: `{{ data.preferred_delivery_time or "—" }}`
  - **Section 5 — Дополнительно**:
    - Особые требования: `{{ data.special_requirements or "—" }}`
    - Срочность: `{{ "Срочно" if data.urgency == "urgent" else "Обычная" }}`
  - **Footer**: line for signature, "Подпись клиента: ___________"
- All text in Russian
- Uses CSS classes (not inline styles) — references `styles.css`
- Handles `None` values gracefully with `or "—"` pattern
- A4 page size set in CSS `@page` rule

**Files created**: `src/voice_bot/templates/rental_request.html`
**Verification**: Render with sample data manually — `jinja2.Template(open(...).read()).render(data=sample, generated_at=...)` produces valid HTML

---

### Step 12. PDF template — CSS (`static/styles.css`)

**Depends on**: Step 11 (HTML references the CSS classes)
**Parallel with**: Step 8, Step 9, Step 10, Step 11

Create `src/voice_bot/static/styles.css`:

- `@page` rule:
  - `size: A4`
  - `margin: 2cm 2.5cm`
  - `@bottom-center` margin box: page number counter
- Body:
  - `font-family: "DejaVu Sans", sans-serif` — available in Docker (fonts-dejavu-core)
  - `font-size: 11pt`
  - `color: #222`
  - `line-height: 1.5`
- `.document-header`:
  - `text-align: center`
  - `font-size: 16pt`
  - `font-weight: bold`
  - `margin-bottom: 20pt`
  - `border-bottom: 2pt solid #333`
  - `padding-bottom: 10pt`
- `.date-line`:
  - `text-align: right`
  - `font-size: 10pt`
  - `color: #666`
  - `margin-bottom: 15pt`
- `.section-title`:
  - `font-weight: bold`
  - `font-size: 12pt`
  - `margin-top: 15pt`
  - `margin-bottom: 8pt`
  - `border-left: 3pt solid #333`
  - `padding-left: 8pt`
- `.field-row`:
  - `margin-bottom: 4pt`
- `.field-label`:
  - `font-weight: bold`
  - `display: inline-block`
  - `min-width: 200pt`
- `.field-value`:
  - `display: inline`
- `table.equipment-table`:
  - `width: 100%`
  - `border-collapse: collapse`
  - `margin-top: 5pt`
- `table.equipment-table th`:
  - `background: #f0f0f0`
  - `border: 1pt solid #ccc`
  - `padding: 6pt`
  - `text-align: left`
- `table.equipment-table td`:
  - `border: 1pt solid #ccc`
  - `padding: 6pt`
- `.urgency-urgent`:
  - `color: #c0392b`
  - `font-weight: bold`
- `.footer`:
  - `margin-top: 40pt`
  - `border-top: 1pt solid #ccc`
  - `padding-top: 10pt`
  - `font-size: 10pt`

**Files created**: `src/voice_bot/static/styles.css`
**Verification**: Visual — render PDF with sample data and inspect (Step 13 generates, Step 22 tests)

---

### Step 13. PDF generator service (`services/pdf_generator.py`)

**Depends on**: Step 5 (models), Step 6 (exceptions), Step 11 (HTML template), Step 12 (CSS)
**Parallel with**: Step 8, Step 9, Step 10

Create `src/voice_bot/services/pdf_generator.py`:

- `PDFGeneratorService` class:
  - `__init__(self)` — sets up Jinja2 `Environment` with `FileSystemLoader` pointing to `templates/` directory (use `pathlib.Path(__file__).parent.parent / "templates"`)
  - `def generate(self, data: RentalRequestData) -> bytes`:
    - Renders `rental_request.html` template with `data` and `generated_at=datetime.now()`
    - Reads `static/styles.css` content
    - Inlines CSS into HTML `<style>` tag (WeasyPrint needs CSS accessible — either inline or via `url_fetcher`)
    - Creates `weasyprint.HTML(string=rendered_html, base_url=str(template_dir))` — `base_url` enables relative URL resolution for CSS
    - Calls `.write_pdf()` → returns `bytes`
    - Raises `PDFGenerationError` on any WeasyPrint exception
    - Logs: start (DEBUG), success (INFO with PDF size in bytes), failure (ERROR)
  - Synchronous method (WeasyPrint is not async — call from async context with `asyncio.to_thread` in the handler)
- Module-level factory: `def create_pdf_generator() -> PDFGeneratorService`

**Files created**: `src/voice_bot/services/pdf_generator.py`
**Verification**: Unit test with sample `RentalRequestData` — see Step 22

---

## Phase D — Bot Layer (Telegram integration)

### Step 14. Access control middleware (`middleware.py`)

**Depends on**: Step 4 (config — `allowed_user_ids`), Step 6 (exceptions — `AccessDeniedError`)
**Parallel with**: Step 9, Step 10, Step 13

Create `src/voice_bot/middleware.py`:

- `AccessControlMiddleware(BaseMiddleware)`:
  - Inherits from `aiogram.BaseMiddleware`
  - `__init__(self, allowed_user_ids: list[int])` — stores the whitelist
  - `async def __call__(self, handler, event, data) -> None`:
    - Extract `event.from_user` (works for both `Message` and `CallbackQuery`)
    - If `from_user.id` not in `allowed_user_ids`:
      - Log WARNING: `"Unauthorized access attempt", user_id=from_user.id, username=from_user.username`
      - If event is a `Message`: send "У вас нет доступа к этому боту."
      - Return (don't call handler)
    - Else: `await handler(event, data)` — proceed to handler
- Registered on `Dispatcher` (or `Router`) for all update types

**Files created**: `src/voice_bot/middleware.py`
**Verification**: Unit test — see Step 23

---

### Step 15. Message handlers (`handlers.py`)

**Depends on**: Step 4 (config), Step 5 (models), Step 6 (exceptions), Step 9 (transcription), Step 10 (extraction), Step 13 (pdf_generator), Step 14 (middleware)
**Parallel with**: nothing (this is the integration point — everything feeds into here)

Create `src/voice_bot/handlers.py`:

- `Router` instance: `router = Router()`
- `handle_voice_message` handler:
  - Filter: `F.voice` (aiogram magic filter for voice messages)
  - Flow:
    1. Send acknowledgment: `await message.answer("Обрабатываю ваше сообщение…")`
    2. Get file info: `await message.bot.get_file(message.voice.file_id)`
    3. Download voice file: `await message.bot.download_file(file.file_path, destination=BytesIO())` → get bytes
    4. Transcribe: `await transcription_service.transcribe(audio_bytes)`
    5. Check for empty transcription → send error message, return
    6. Extract entities: `await extraction_service.extract(transcript)`
    7. Check for empty data (all fields None, no equipment) → send "Не удалось извлечь данные", return
    8. Generate PDF: `await asyncio.to_thread(pdf_generator.generate, rental_data)` (offload sync WeasyPrint to thread)
    9. Send PDF: `await message.answer_document(BufferedInputFile(pdf_bytes, filename="zayavka_na_arendu.pdf"), caption="Ваша заявка на аренду готова")`
  - Error handling: try/except around each step, catch specific exceptions, send user-friendly Russian error message, log full error
  - Log: each step with timing (DEBUG), final success (INFO)
- `handle_start` handler:
  - Filter: `CommandStart()`
  - Sends welcome message: "Здравствуйте! Отправьте голосовое сообщение с заявкой на аренду строительной техники, и я создам для вас PDF документ."
- `handle_help` handler:
  - Filter: `Command("help")`
  - Sends help text: instructions, what to include in voice message, example
- `handle_non_voice` handler:
  - Filter: `~F.voice` (catch-all for non-voice messages)
  - Sends: "Этот бот принимает только голосовые сообщения. Отправьте голосовое сообщение с вашей заявкой."

**Files created**: `src/voice_bot/handlers.py`
**Verification**: Unit test with mocked services — see Step 24

---

### Step 16. Bot setup + lifecycle (`bot.py`)

**Depends on**: Step 4 (config), Step 8 (logging), Step 14 (middleware), Step 15 (handlers)
**Parallel with**: nothing

Create `src/voice_bot/bot.py`:

- `create_bot() -> Bot`:
  - `Bot(token=settings.telegram_bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))`
- `create_dispatcher(bot, services) -> Dispatcher`:
  - `Dispatcher(bot)`
  - Register `AccessControlMiddleware` on dispatcher
  - Include `router` from `handlers.py`
  - Return dispatcher
- `async def run_polling(bot, dp) -> None`:
  - Called when `settings.use_webhook == False`
  - `await bot.delete_webhook()` — clear any existing webhook
  - `await dp.start_polling(bot)`
- `async def run_webhook(bot, dp) -> None`:
  - Called when `settings.use_webhook == True`
  - Build webhook URL: `f"{settings.webhook_url}{settings.webhook_path}"`
  - `await bot.set_webhook(url=webhook_url, secret_token=settings.webhook_secret)`
  - Create `aiohttp.web.Application()`
  - Register `SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=settings.webhook_secret)` at `settings.webhook_path`
  - Register `/healthz` endpoint: returns `{"status": "ok"}` as JSON
  - Register startup/shutdown hooks (close OpenAI clients, close bot session)
  - `web.run_app(app, host="0.0.0.0", port=settings.port)`
- Service lifecycle:
  - Create `TranscriptionService`, `ExtractionService`, `PDFGeneratorService` instances
  - Pass to dispatcher/handlers via `workflow_data` or closure
  - On shutdown: `await transcription_service.close()`, `await extraction_service.close()`, `await bot.session.close()`

**Files created**: `src/voice_bot/bot.py`
**Verification**: Bot starts in polling mode with valid token (manual test)

---

### Step 17. Entry point (`__main__.py`)

**Depends on**: Step 16
**Parallel with**: nothing

Create `src/voice_bot/__main__.py`:

- `def main() -> None`:
  - Call `setup_logging(settings.log_level)`
  - Log: "Starting voice bot" with mode (webhook/polling)
  - Create bot, dispatcher, services
  - If `settings.use_webhook`: `asyncio.run(run_webhook(bot, dp))`
  - Else: `asyncio.run(run_polling(bot, dp))`
- `if __name__ == "__main__": main()`
- Wrap in try/except `KeyboardInterrupt` for clean shutdown

**Files created**: `src/voice_bot/__main__.py`
**Verification**: `python -m voice_bot` starts without import errors (will fail at API call if no valid token, but imports and startup should work)

---

## Phase E — Tests

### Step 18. Test fixtures (`conftest.py`)

**Depends on**: Steps 4-17 (needs all modules to exist)
**Parallel with**: nothing (all test steps depend on this)

Create `tests/conftest.py`:

- Fixtures:
  - `mock_settings` — `monkeypatch` env vars, return `Settings` instance with test values
  - `sample_rental_data` — returns a fully populated `RentalRequestData` for PDF tests
  - `empty_rental_data` — returns `RentalRequestData()` with all defaults
  - `sample_transcript` — Russian text simulating a Whisper transcription
  - `mock_openai_client` — `AsyncMock` of `AsyncOpenAI` for transcription/extraction tests
  - `mock_bot` — `AsyncMock` of `aiogram.Bot` for handler tests
  - `mock_message` — `MagicMock` of `aiogram.types.Message` with `.voice`, `.answer()`, `.answer_document()`
  - `pdf_generator` — real `PDFGeneratorService` instance (WeasyPrint is local, no mocking needed)
- `pytest-asyncio` configured via `pyproject.toml` (`asyncio_mode = "auto"`)

**Files created**: `tests/conftest.py`
**Verification**: `pytest --collect-only` finds all test files without import errors

---

### Step 19. Tests: config (`test_config.py`)

**Depends on**: Step 18
**Parallel with**: Steps 20, 21, 22, 23, 24

Create `tests/test_config.py`:

- `test_settings_load_from_env` — set env vars, verify `Settings` fields
- `test_settings_load_from_dotenv` — create temp `.env`, verify loading
- `test_settings_missing_required_raises` — remove `TELEGRAM_BOT_TOKEN`, expect `ValidationError`
- `test_allowed_user_ids_parsing` — set `ALLOWED_USER_IDS="123,456,789"`, verify `list[int]`
- `test_webhook_mode_validation` — `use_webhook=True` without `webhook_url` → `ValidationError`
- `test_default_values` — verify `webhook_path`, `log_level`, `port` defaults

**Files created**: `tests/test_config.py`
**Verification**: `pytest tests/test_config.py -v` — all tests pass

---

### Step 20. Tests: transcription service (`test_transcription.py`)

**Depends on**: Step 18
**Parallel with**: Steps 19, 21, 22, 23, 24

Create `tests/test_transcription.py`:

- `test_transcribe_success` — mock `AsyncOpenAI.audio.transcriptions.create` returns text, verify output
- `test_transcribe_empty_audio` — mock returns empty string, verify empty string returned
- `test_transcribe_api_error` — mock raises `openai.APIError`, verify `TranscriptionError` raised
- `test_transcribe_timeout` — mock raises `httpx.TimeoutException`, verify `TranscriptionError` raised
- `test_transcribe_passes_language_ru` — verify the `language="ru"` parameter is passed to API
- `test_transcribe_passes_whisper_model` — verify `model="whisper-1"` is passed

**Files created**: `tests/test_transcription.py`
**Verification**: `pytest tests/test_transcription.py -v` — all tests pass

---

### Step 21. Tests: extraction service (`test_extraction.py`)

**Depends on**: Step 18
**Parallel with**: Steps 19, 20, 22, 23, 24

Create `tests/test_extraction.py`:

- `test_extract_success` — mock `chat.completions.parse` returns `RentalRequestData` with sample fields, verify parsed output
- `test_extract_returns_none` — mock returns `parsed=None`, verify `ExtractionError` raised
- `test_extract_api_error` — mock raises `openai.APIError`, verify `ExtractionError` raised
- `test_extract_passes_system_prompt` — verify messages contain `SYSTEM_PROMPT` as system role
- `test_extract_passes_gpt4o_mini_model` — verify `model="gpt-4o-mini"` is passed
- `test_extract_passes_temperature_zero` — verify `temperature=0` is passed
- `test_extract_passes_response_format` — verify `response_format=RentalRequestData` is passed

**Files created**: `tests/test_extraction.py`
**Verification**: `pytest tests/test_extraction.py -v` — all tests pass

---

### Step 22. Tests: PDF generator (`test_pdf_generator.py`)

**Depends on**: Step 18
**Parallel with**: Steps 19, 20, 21, 23, 24

Create `tests/test_pdf_generator.py`:

- `test_generate_pdf_returns_bytes` — call with `sample_rental_data`, verify return type is `bytes`
- `test_generate_pdf_valid_header` — verify PDF starts with `%PDF` magic bytes
- `test_generate_pdf_contains_client_name` — render with sample data, extract text from PDF, verify client name appears
- `test_generate_pdf_contains_equipment` — verify equipment names appear in PDF text
- `test_generate_pdf_empty_data` — call with `empty_rental_data`, verify no crash, PDF still generated (with "—" placeholders)
- `test_generate_pdf_cyrillic_text` — verify Russian text renders correctly (not as tofu boxes) — check that Cyrillic characters are present in PDF content stream
- `test_generate_pdf_error_handling` — mock WeasyPrint to raise, verify `PDFGenerationError`

**Files created**: `tests/test_pdf_generator.py`
**Verification**: `pytest tests/test_pdf_generator.py -v` — all tests pass

---

### Step 23. Tests: middleware (`test_middleware.py`)

**Depends on**: Step 18
**Parallel with**: Steps 19, 20, 21, 22, 24

Create `tests/test_middleware.py`:

- `test_allowed_user_passes` — user ID in whitelist, verify handler is called
- `test_blocked_user_rejected` — user ID not in whitelist, verify handler is NOT called
- `test_blocked_user_gets_message` — verify `message.answer()` called with access denied text
- `test_blocked_user_logged` — verify WARNING log emitted (use `caplog`)

**Files created**: `tests/test_middleware.py`
**Verification**: `pytest tests/test_middleware.py -v` — all tests pass

---

### Step 24. Tests: handlers (`test_handlers.py`)

**Depends on**: Step 18
**Parallel with**: Steps 19, 20, 21, 22, 23

Create `tests/test_handlers.py`:

- `test_handle_voice_full_flow` — mock all services, simulate voice message, verify:
  - Acknowledgment message sent
  - `bot.get_file` called
  - `bot.download_file` called
  - `transcription_service.transcribe` called with audio bytes
  - `extraction_service.extract` called with transcript
  - `pdf_generator.generate` called with `RentalRequestData`
  - `message.answer_document` called with PDF bytes
- `test_handle_voice_transcription_error` — mock transcription to raise `TranscriptionError`, verify user gets error message, no PDF sent
- `test_handle_voice_extraction_error` — mock extraction to raise, verify error message
- `test_handle_voice_pdf_error` — mock PDF generator to raise, verify error message
- `test_handle_voice_empty_transcript` — mock transcription returns "", verify "Не удалось распознать речь" message
- `test_handle_start` — verify welcome message sent
- `test_handle_help` — verify help text sent
- `test_handle_non_voice` — verify "only voice" message sent

**Files created**: `tests/test_handlers.py`
**Verification**: `pytest tests/test_handlers.py -v` — all tests pass

---

## Phase F — Deployment Infrastructure

### Step 25. Dockerfile

**Depends on**: Steps 1-17 (needs complete source code + pyproject.toml)
**Parallel with**: Step 26, Step 27

Create `Dockerfile`:

- Multi-stage build (builder + runtime) as specified in Overview.md
- Builder stage: `python:3.12-slim`, install `build`, run `python -m build --wheel`
- Runtime stage: `python:3.12-slim` + WeasyPrint system deps + fonts-dejavu-core + fontconfig
- Non-root user (`app`)
- Copy wheel from builder, install, copy `src/`
- `EXPOSE 8080`
- `CMD ["python", "-m", "voice_bot"]`
- `.dockerignore` excludes tests, docs, .git, .env

**Files created**: `Dockerfile`
**Verification**: `docker build -t voice-bot .` succeeds; `docker run --rm voice-bot python -c "import voice_bot; print('ok')"` prints ok

---

### Step 26. GitHub Actions CI/CD (`.github/workflows/deploy.yml`)

**Depends on**: Steps 1-24 (needs tests to exist for CI to run)
**Parallel with**: Step 25, Step 27

Create `.github/workflows/deploy.yml`:

- Two jobs: `test` and `deploy` (deploy depends on test)
- **test job**:
  - Checkout, setup Python 3.12
  - `pip install -e ".[dev]"`
  - `ruff check .`
  - `ruff format --check .`
  - `mypy src/`
  - `pytest --cov=src/ --cov-report=term-missing`
- **deploy job** (only on `main` branch):
  - Checkout
  - Auth via Workload Identity Federation (`google-github-actions/auth@v2`)
  - Setup gcloud
  - Configure Docker for Artifact Registry
  - Build and push image tagged with `${{ github.sha }}`
  - Deploy to Cloud Run via `google-github-actions/deploy-cloudrun@v2`
  - Set secrets from Secret Manager
  - Set env vars: `USE_WEBHOOK=true`, `WEBHOOK_URL`, `WEBHOOK_PATH=/webhook`
  - `--no-allow-unauthenticated` (webhook is authenticated via secret token)

**Files created**: `.github/workflows/deploy.yml`
**Verification**: YAML lint; on push to main, CI runs (requires GCP setup)

---

### Step 27. README

**Depends on**: Steps 1-26 (documents the complete project)
**Parallel with**: Step 25, Step 26

Create `README.md`:

- Project description (what it does, who it's for)
- Prerequisites (Python 3.12+, Telegram Bot Token, OpenAI API key, Google Cloud project)
- Local development setup:
  1. Clone repo
  2. Create `.env` from `.env.example`
  3. Fill in `TELEGRAM_BOT_TOKEN`, `OPENAI_API_KEY`, `ALLOWED_USER_IDS`
  4. `pip install -e ".[dev]"`
  5. `python -m voice_bot` (runs in polling mode)
- Testing: `pytest -v`
- Linting: `ruff check . && ruff format --check . && mypy src/`
- Docker build: `docker build -t voice-bot .`
- Google Cloud deployment:
  1. Enable APIs (Cloud Run, Artifact Registry, Secret Manager)
  2. Create secrets in Secret Manager
  3. Set up Workload Identity Federation
  4. Configure GitHub Actions variables
  5. Push to main → CI/CD deploys automatically
- Architecture summary (link to Overview.md)
- Implementation plan (link to PLAN.md)

**Files created**: `README.md`
**Verification**: Manual review — all instructions are accurate and followable

---

## Execution Order

Steps are listed in execution order. Steps on the **same line** can be executed in parallel.

```
Step 1
  └─ Step 2, Step 3
       └─ Step 4, Step 5, Step 6
            ├─ Step 7 (needs Step 5)
            ├─ Step 8 (needs Step 4)
            ├─ Step 9 (needs Step 4, Step 6)
            ├─ Step 10 (needs Step 4, Step 5, Step 6, Step 7)
            ├─ Step 11 (needs Step 5)
            │    └─ Step 12 (needs Step 11)
            │         └─ Step 13 (needs Step 5, Step 6, Step 11, Step 12)
            └─ Step 14 (needs Step 4, Step 6)
                 └─ Step 15 (needs Step 4, 5, 6, 9, 10, 13, 14)
                      └─ Step 16 (needs Step 4, 8, 14, 15)
                           └─ Step 17 (needs Step 16)
                                └─ Step 18 (needs all source modules)
                                     ├─ Step 19, Step 20, Step 21, Step 22, Step 23, Step 24  (all parallel)
                                          └─ Step 25, Step 26, Step 27  (all parallel)
```

### Linear execution (if doing one at a time):

1. **Step 1** — `pyproject.toml`
2. **Step 2** — `.gitignore`, `.env.example`, `.dockerignore`
3. **Step 3** — Package `__init__.py` files
4. **Step 4** — `config.py`
5. **Step 5** — `models.py`
6. **Step 6** — `exceptions.py`
7. **Step 7** — `prompts.py`
8. **Step 8** — `logging_config.py`
9. **Step 9** — `services/transcription.py`
10. **Step 10** — `services/extraction.py`
11. **Step 11** — `templates/rental_request.html`
12. **Step 12** — `static/styles.css`
13. **Step 13** — `services/pdf_generator.py`
14. **Step 14** — `middleware.py`
15. **Step 15** — `handlers.py`
16. **Step 16** — `bot.py`
17. **Step 17** — `__main__.py`
18. **Step 18** — `tests/conftest.py`
19. **Step 19** — `tests/test_config.py`
20. **Step 20** — `tests/test_transcription.py`
21. **Step 21** — `tests/test_extraction.py`
22. **Step 22** — `tests/test_pdf_generator.py`
23. **Step 23** — `tests/test_middleware.py`
24. **Step 24** — `tests/test_handlers.py`
25. **Step 25** — `Dockerfile`
26. **Step 26** — `.github/workflows/deploy.yml`
27. **Step 27** — `README.md`

### Parallel execution groups:

| Group | Steps | Rationale |
|---|---|---|
| A | 1 | Foundation — nothing can start without pyproject.toml |
| B | 2, 3 | Independent config files and package markers |
| C | 4, 5, 6 | Core domain modules — no interdependencies |
| D | 7, 8, 9, 11, 14 | D depends only on C modules; 7 needs 5, 8 needs 4, 9 needs 4+6, 11 needs 5, 14 needs 4+6 |
| E | 10, 12, 13 | E depends on D; 10 needs 4+5+6+7, 12 needs 11, 13 needs 5+6+11+12 |
| F | 15 | Integration point — needs all services + middleware |
| G | 16 | Bot wiring — needs handlers + middleware + logging |
| H | 17 | Entry point — needs bot |
| I | 18 | Test fixtures — needs all source modules |
| J | 19, 20, 21, 22, 23, 24 | All tests in parallel — each tests one module |
| K | 25, 26, 27 | Deployment infra — needs complete project |
