FROM python:3.11-slim

WORKDIR /app

# Install CPU-only PyTorch first (avoids 2GB+ CUDA download)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# Install other dependencies
COPY core/learning_loop/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared common utilities and learning loop code
COPY core/common /app/core/common
COPY core/learning_loop /app/core/learning_loop

# Set Python path
ENV PYTHONPATH=/app

# Run the unified learning loop
CMD ["python", "-m", "core.learning_loop.main"]
