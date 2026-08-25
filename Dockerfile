# ============================================================
# RDE Platform — Dockerfile
# Imagem base: Python 3.13 slim (menor tamanho)
# ============================================================
FROM python:3.13-slim

# Evita prompts interativos durante instalação de pacotes do sistema
ENV DEBIAN_FRONTEND=noninteractive

# Variáveis de ambiente do Python
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Diretório de trabalho dentro do container
WORKDIR /app

# Instala dependências do sistema necessárias para alguns pacotes Python
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Copia apenas o requirements primeiro (melhor uso do cache do Docker)
COPY requirements.txt .

# Instala as dependências Python
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copia o restante do código fonte
COPY . .

# Porta exposta pela aplicação
EXPOSE 8000

# Cria pasta para o banco de dados SQLite com permissão de escrita
RUN mkdir -p /data && chmod 777 /data

# Comando de inicialização
CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
