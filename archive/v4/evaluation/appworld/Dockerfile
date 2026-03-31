FROM python:3.12-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl && rm -rf /var/lib/apt/lists/*

# Python dependencies (cached layer) - install first to pin click/typer versions
COPY evaluation/appworld/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# AppWorld setup (already installed via requirements, just run setup commands)
RUN appworld install && \
    appworld download data

# Runner code - this is a standalone client, no ALEC internal dependencies
# Communicates only via session HTTP API
COPY evaluation/appworld .

# Copy evaluation/database for database connection module
COPY evaluation/database /app/database

CMD ["python", "-m", "runner"]
