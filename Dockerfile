FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml ./
COPY alembic.ini ./
COPY src ./src
COPY tests ./tests
COPY migrations ./migrations
COPY content ./content
RUN pip install --no-cache-dir -e ".[dev]"

CMD ["uvicorn", "funnelhub.main:app", "--host", "0.0.0.0", "--port", "8000"]
