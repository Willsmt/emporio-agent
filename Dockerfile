FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOST=0.0.0.0 \
    PORT=8000

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
COPY data/raw ./data/raw
COPY data/curated ./data/curated

# Editable install keeps the src/ layout, so the app finds data/ relative to the project root.
RUN pip install -e . \
    && python -m emporio.data.etl \
    && useradd --create-home --uid 10001 app \
    && chown -R app /app/data/processed

USER app
EXPOSE 8000

# LLM_PROVIDER, LLM_API_KEY (and optionally LLM_MODEL) must be provided as platform secrets.
CMD ["python", "-m", "emporio.web"]
