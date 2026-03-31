FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for caching
COPY core/session/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy common modules (kafka_client now in core/common)
COPY core/common /app/core/common

# Copy service code
COPY core/session /app/core/session

# Environment
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8008/health || exit 1

# Run service
EXPOSE 8008
CMD ["python", "-m", "uvicorn", "core.session.main:app", "--host", "0.0.0.0", "--port", "8008"]
