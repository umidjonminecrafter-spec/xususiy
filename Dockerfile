# ==============================================================================
# Multi-stage Production Dockerfile for SmartTalim Django Backend
# ==============================================================================

FROM python:3.12-slim AS builder

WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --user -r requirements.txt

# --- Final Production Image ---
FROM python:3.12-slim AS final

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/root/.local/bin:$PATH

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed python packages from builder
COPY --from=builder /root/.local /root/.local

# Copy application source code
COPY . .

# Ensure static and media directories exist
RUN mkdir -p /app/staticfiles /app/media

# Expose Django port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health/ || exit 1

# Default command: Run database migrations, collectstatic, and start Gunicorn
CMD ["sh", "-c", "python manage.py collectstatic --no-input && python manage.py migrate && gunicorn -c gunicorn.conf.py config.wsgi:application"]
