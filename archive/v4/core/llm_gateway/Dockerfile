FROM python:3.11-slim

WORKDIR /app

# Install CPU-only torch first to avoid CUDA bloat (~200MB vs ~2GB)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

COPY core/llm_gateway/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY core/__init__.py /app/core/__init__.py
COPY core/common /app/core/common
COPY core/llm_gateway /app/core/llm_gateway

CMD ["sh", "-c", "uvicorn core.llm_gateway.api.main:app --host 0.0.0.0 --port 8000 ${UVICORN_RELOAD_FLAG}"]
