# Stage 1: Builder
FROM python:3.11-slim as builder

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends gcc

COPY requirements.txt .
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /app/wheels -r requirements.txt

# Stage 2: Runtime (Distroless-like or Slim)
FROM python:3.11-slim

WORKDIR /app

COPY --from=builder /app/wheels /wheels
COPY --from=builder /app/requirements.txt .

RUN pip install --no-cache /wheels/*

COPY app/ ./app/

# Create a non-root user for security
RUN adduser --disabled-password --gecos '' appuser
USER appuser

EXPOSE 8000

# Run using Uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
