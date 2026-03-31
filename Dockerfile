FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml .
COPY alec/ alec/

# Install CPU-only PyTorch first (avoids pulling ~2GB CUDA torch)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir ".[embeddings]"

EXPOSE 8000

CMD ["python", "-m", "alec.api.main"]
