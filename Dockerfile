# Stage 1: Build frontend
FROM node:22-alpine AS frontend-builder

WORKDIR /ui

COPY ui/package.json ui/package-lock.json ./

RUN npm ci

COPY ui/ ./

RUN npm run build

# Stage 2: Build Python app
FROM python:3.11-slim AS app

WORKDIR /app

# Build dependencies for native extensions (sentence-transformers, chromadb)
RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Install dependencies (cached layer — only rebuilds when pyproject.toml changes)
COPY pyproject.toml ./
RUN mkdir -p src/context_library && touch src/context_library/__init__.py
# Install CPU-only torch first to prevent pip from pulling large NVIDIA CUDA packages
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir ".[server]"

# Pre-download the default embedding model into the image
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# Copy built frontend assets from the frontend-builder stage
COPY --from=frontend-builder /ui/dist/ /app/ui/dist/

# Copy Python source code
COPY src/ ./src/

# Data directories (mounted as volumes at runtime)
RUN mkdir -p /data/sqlite /data/chromadb

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    CTX_SQLITE_DB_PATH=/data/sqlite/documents.db \
    CTX_CHROMADB_PATH=/data/chromadb \
    CTX_HOST=0.0.0.0 \
    CTX_PORT=8000

EXPOSE 8000

CMD ["uvicorn", "context_library.server.app:app", "--host", "0.0.0.0", "--port", "8000"]
