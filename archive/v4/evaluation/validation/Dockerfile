FROM python:3.12-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Runner code
COPY . .

# Set PYTHONPATH for absolute imports
ENV PYTHONPATH=/app

# Entry point - arguments passed via docker run
ENTRYPOINT ["python", "-m", "runner"]

# Default command (validate)
CMD ["validate"]
