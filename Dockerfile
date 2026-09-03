# --- Builder stage ---
FROM python:3.12-slim AS builder

WORKDIR /build

# Copy project metadata and source code needed to build the wheel
COPY pyproject.toml ./
COPY src/ src/

# Build the wheel (project only; dependencies are resolved at install time)
RUN pip wheel . --no-deps -w dist/

# --- Runtime stage ---
FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.title="voice-bot" \
      org.opencontainers.image.description="Telegram voice-to-PDF bot for construction equipment rental" \
      org.opencontainers.image.source="https://github.com/VitalyKlepcha/stt-rental-bot"

# WeasyPrint system dependencies + Cyrillic-capable fonts
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

# Copy and install the wheel, then remove it
COPY --from=builder /build/dist/*.whl ./
RUN pip install --no-cache-dir *.whl && rm *.whl

# Copy source directory (includes templates and static files for WeasyPrint)
COPY src/ src/

# Set ownership and switch to non-root user
RUN chown -R app:app /app
USER app

EXPOSE 8080

CMD ["python", "-m", "voice_bot"]
