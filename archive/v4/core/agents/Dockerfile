FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY core/agents/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared common utilities and agents code
COPY core/common /app/core/common
COPY core/agents /app/core/agents
# Copy full learning_loop for shared utilities and service imports
COPY core/learning_loop /app/core/learning_loop

# Set Python path
ENV PYTHONPATH=/app

# Run the unified agents service
CMD ["python", "-m", "core.agents.main"]
