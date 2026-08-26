# ============================================================
# RDE Platform — Dockerfile Multi-Stage Build
# ============================================================

# --- Stage 1: Build do Frontend Next.js ---
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci || npm install
COPY frontend ./
RUN npm run build

# --- Stage 2: Servidor Python FastAPI ---
FROM python:3.13-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    git \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

# Copia o build estático gerado no Stage 1 diretamente para cliente/frontend
COPY --from=frontend-builder /app/frontend/out ./cliente/frontend

EXPOSE 8000

RUN mkdir -p /data && chmod 777 /data

CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
