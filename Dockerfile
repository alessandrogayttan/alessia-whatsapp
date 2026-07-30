FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p data

ENV FLASK_ENV=production
ENV PORT=8080

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT}/health" || exit 1

# gthread: health/webhook no se bloquean si un job de Sheets tarda
CMD gunicorn --bind "0.0.0.0:${PORT}" --worker-class gthread --workers 1 --threads 4 --timeout 60 --graceful-timeout 20 wsgi:app
