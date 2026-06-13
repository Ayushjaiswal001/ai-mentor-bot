# Hugging Face Spaces (Docker SDK) — listens on 7860 for the health check.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY pyproject.toml ./
COPY app ./app
COPY content ./content

RUN pip install --no-cache-dir . && \
    useradd -m -u 1000 botuser && \
    mkdir -p /app/data && chown -R botuser:botuser /app

USER botuser
EXPOSE 7860

CMD ["python", "-m", "app.main"]
