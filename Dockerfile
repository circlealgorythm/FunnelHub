FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src

WORKDIR /app

COPY pyproject.toml ./
RUN mkdir -p src/funnelhub && touch src/funnelhub/__init__.py \
    && pip install --no-cache-dir -e ".[dev]"

COPY alembic.ini ./
COPY src ./src
COPY tests ./tests
COPY migrations ./migrations
COPY content ./content
COPY public ./public
COPY inbox-app/dist ./inbox-app/dist

CMD ["uvicorn", "funnelhub.main:app", "--host", "0.0.0.0", "--port", "8000"]
