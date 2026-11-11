# syntax=docker/dockerfile:1
# Orders service: cart checkout, orders and fake payment.
# Build context is this folder: docker build -t orders services/orders

FROM python:3.12-slim

# No .pyc files in the image; print logs immediately so stdout is not buffered.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

# Unprivileged user. The service never needs to write to its own code.
RUN useradd --create-home --uid 10001 appuser

# Dependencies before source, so editing code does not reinstall packages.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Only what the service needs to run: the package and its migrations.
# No tests, no .env, no local database.
COPY orders/ ./orders/
COPY migrations/ ./migrations/

# Commit SHA, reported by /health as "version". CI passes --build-arg GIT_SHA.
ARG GIT_SHA=dev
ENV GIT_SHA=${GIT_SHA}

USER appuser

EXPOSE 8000

# Used by docker compose; Azure Container Apps uses its own probes.
HEALTHCHECK --interval=15s --timeout=3s --start-period=60s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/health', timeout=2)" || exit 1

# sh -c so ${PORT} is expanded at run time; exec so gunicorn becomes PID 1
# and receives SIGTERM directly when the container stops.
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT} --workers 2 --timeout 90 'orders:create_app()'"]
