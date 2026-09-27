# Render free tier: 512MB RAM. No Playwright browsers installed on purpose —
# live GMP degrades gracefully to "Data unavailable" (fail-soft by design).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    AUTO_SEED=1

WORKDIR /app
# Repo root IS the package, so nest it under its package name for imports.
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY . /app/nse_ipo_analyzer/

EXPOSE 8000
CMD ["sh", "-c", "uvicorn nse_ipo_analyzer.api.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
