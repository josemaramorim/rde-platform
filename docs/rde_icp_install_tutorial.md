# 🚀 RDE Platform — Tutorial de Instalação Completa no Painel ICP

> **Versão**: RDE Platform v5  
> **Backend**: FastAPI + Uvicorn (Python 3.13)  
> **Frontend**: Next.js (build estático)  
> **Banco**: SQLite com volume Docker persistente  
> **Deploy**: Docker via GitHub Container Registry (GHCR) + ICP Compose

---

## ⚙️ Requisitos Mínimos no ICP

| Recurso | Requisito |
|---------|-----------|
| **Container Docker** | Suporte a Docker Compose (aba "Compose" no ICP) |
| **GitHub** | Repositório com GitHub Actions habilitado |
| **Domínio / HTTPS** | Domínio próprio com SSL (Let's Encrypt) |
| **Portas** | 8000 (backend) ou proxy reverso via OpenResty/Nginx |

> [!IMPORTANT]
> O RDE Platform **NÃO funciona em hospedagem serverless**. A aplicação mantém conexões WebSocket persistentes com as corretoras e o Telegram.

---

## 📁 ETAPA 1 — Preparar o Repositório no GitHub

### 1.1 — Revisar o `.gitignore`

```gitignore
.env
.env.*
!.env.example
*.db
*.db-wal
*.db-shm
*.sqlite3
*.session
*.session-journal
*.log
live_status_*.json
live_operations_*.json
copier.pid
__pycache__/
*.pyc
.venv/
.venv.linux/
node_modules/
.next/
.vscode/
.idea/
rde-frontend_old_FAT32/
```

### 1.2 — Criar o `requirements.txt`

> [!NOTE]
> Não use `pip freeze` do `.venv` se ele estiver apontando para Python de outro usuário. O arquivo foi gerado por análise estática dos imports.

```txt
fastapi>=0.111.0
uvicorn[standard]>=0.30.0
fastapi-users[sqlalchemy]>=13.0.0
sqlalchemy>=2.0.0
aiosqlite>=0.19.0
alembic>=1.13.0
pydantic>=2.7.0
pydantic-settings>=2.3.0
python-dotenv>=1.0.0
cryptography>=42.0.0
passlib[bcrypt]>=1.7.4
python-jose[cryptography]>=3.3.0
celery>=5.3.0
redis>=5.0.0
kombu>=5.3.0
requests>=2.31.0
aiohttp>=3.9.0
websocket-client>=1.8.0
websockets>=12.0
telethon>=1.36.0
stripe>=9.0.0
fastapi-mail>=1.4.0
aiosmtplib>=3.0.0
numpy>=1.26.0
scikit-learn>=1.4.0
slowapi>=0.1.9
boto3>=1.34.0
hvac>=2.1.0
python-multipart>=0.0.9
httpx>=0.27.0
```

### 1.3 — Criar o `Dockerfile`

```dockerfile
FROM python:3.13-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libffi-dev libssl-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Cria pasta para o banco SQLite com permissão de escrita
RUN mkdir -p /data && chmod 777 /data

CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
```

### 1.4 — Criar o GitHub Action (`.github/workflows/docker-publish.yml`)

```yaml
name: Build & Publish Docker Image

on:
  push:
    branches: [ "main" ]

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  build-and-push:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write

    steps:
      - name: Checkout do repositório
        uses: actions/checkout@v4

      - name: Login no GitHub Container Registry
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Extrair metadados da imagem
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
          tags: |
            type=raw,value=latest
            type=sha,prefix=sha-

      - name: Build e Push da imagem Docker
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
```

### 1.5 — Push para o GitHub

```powershell
# Se a branch local for "master", renomeie para "main"
git branch -M main

git add .
git commit -m "feat: RDE Platform v5 — deploy inicial para ICP"
git push -u origin main
```

> [!WARNING]
> Se der erro `src refspec main does not match any`, é porque a branch local é `master`. Execute `git branch -M main` antes do push.

> [!TIP]
> Acompanhe o build da imagem em: `https://github.com/josemaramorim/rde-platform/actions`  
> Aguarde o ícone ficar ✅ verde (~3 minutos) antes de fazer o deploy no ICP.

---

## 🐳 ETAPA 2 — Configurar o Deploy no ICP via Docker Compose

### 2.1 — Onde configurar no ICP

> [!IMPORTANT]
> **NÃO use** a aba "Standalone Python" — ela tem problemas de separação entre build e runtime que impedem o uvicorn de funcionar.  
> Use: **Aplicações → Container → aba Compose**

1. Faça login no painel ICP
2. Menu lateral → **Aplicações** → **Container** → aba **Compose**
3. Clique em **Criar**

### 2.2 — Preencher o formulário

| Campo | Valor |
|-------|-------|
| **Pasta** | `rde-platform` |
| **De** | Selecione **Editar** |

### 2.3 — Conteúdo do Compose para o ICP

Cole no editor do ICP:

```yaml
version: "3.9"

services:
  rde-platform:
    image: ghcr.io/josemaramorim/rde-platform:latest
    container_name: rde-platform
    restart: unless-stopped
    ports:
      - "8000:8000"
    env_file:
      - icontainer.env
    environment:
      - DATABASE_URL=sqlite+aiosqlite:////data/rde_local.db
    volumes:
      - rde_db:/data

volumes:
  rde_db:
```

> [!IMPORTANT]
> O `DATABASE_URL` usa **4 barras** (`////data/`) — caminho absoluto no Linux dentro do Docker.  
> O campo `environment` sobrescreve o `icontainer.env`, garantindo que o banco use `/data/`.  
> O volume `rde_db` garante persistência entre reinicializações.

### 2.4 — Campo Ambiente do ICP

```
SECRET_KEY=SEU_SECRET_KEY_AQUI
ENCRYPTION_KEY=SEU_ENCRYPTION_KEY_AQUI
RDE_PROFILE=admin
TELEGRAM_BOT_TOKEN=SEU_TOKEN
TELEGRAM_CHAT_ID=-100XXXXXXXXXX
TELEGRAM_API_ID=SEU_API_ID
TELEGRAM_API_HASH=SEU_API_HASH
TELEGRAM_PHONE=+55XXXXXXXXXXX
MAIL_USERNAME=seu@email.com
MAIL_PASSWORD=SENHA
MAIL_FROM=seu@email.com
MAIL_SERVER=smtp.office365.com
MAIL_PORT=587
MAIL_USE_TLS=True
RATE_LIMIT_ENABLED=True
ADMIN_SERVER_URL=https://seu-dominio.com.br
NEXT_PUBLIC_API_URL=https://seu-dominio.com.br
```

> [!NOTE]
> **Não adicione** `DATABASE_URL` aqui — ela já está no campo `environment` do compose acima.

### 2.5 — Confirmar e verificar

Clique em **Confirmar** e aguarde o log mostrar:
```
docker-compose up successful!
```

---

## ✅ ETAPA 3 — Verificar o Deploy

### 3.1 — Log esperado de sucesso

```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete.
INFO:     Application startup complete.
```

> O aviso `Arquivo de ambiente '.env.admin' não encontrado` é **normal** — container usa `icontainer.env`.

### 3.2 — Testar Health Check

```
http://vps10755.panel.icontainer.run:8000/health
```
Resposta esperada: `{"status": "ok"}`

### 3.3 — Testar Swagger UI

```
http://vps10755.panel.icontainer.run:8000/docs
```

---

## 🔄 ETAPA 4 — Atualizar a Aplicação

```powershell
git add .
git commit -m "fix: descrição da mudança"
git push
```

1. Aguardar GitHub Action completar (~3 min) em `https://github.com/josemaramorim/rde-platform/actions`
2. No ICP Compose → **Editar** → **Confirmar** (força `docker compose pull` com a nova imagem)

---

## 🌐 ETAPA 5 — Configurar Domínio com HTTPS

No painel ICP:
1. **Server** → **OpenResty** → **Criar Site**
2. Preencha seu domínio
3. Configure **Reverse Proxy** apontando para: `http://127.0.0.1:8000`
4. Ative **SSL** (Let's Encrypt gratuito)

---

## 🗄️ ETAPA 6 — Inicializar o Banco de Dados

No terminal do container (via ICP):

```bash
# Criar tabelas
python -c "
import sys, asyncio; sys.path.insert(0, '.')
from src.database.session import engine
from src.models.user import Base as UBase
from src.models.broker import Base as BBase
async def create():
    async with engine.begin() as conn:
        await conn.run_sync(UBase.metadata.create_all)
        await conn.run_sync(BBase.metadata.create_all)
    print('Tabelas criadas!')
asyncio.run(create())
"

# Criar planos Free/Pro/VIP
python -m src.seed_plans

# Criar usuário administrador
python -m src.create_admin
```

---

## 🔧 Problemas Conhecidos e Soluções

| Erro | Causa | Solução |
|------|-------|---------|
| `src refspec main does not match any` | Branch local é `master` | `git branch -M main` antes do push |
| `No module named uvicorn` | Build e runtime são containers separados | Usar aba **Compose** com imagem do GHCR |
| `unable to open database file` | SQLite sem permissão de escrita no container | `DATABASE_URL=sqlite+aiosqlite:////data/rde_local.db` + volume `/data` |
| `O build não gerou arquivos na saída configurada` | Standalone Python com output dir inválido | Usar aba **Compose** em vez de Standalone |
| CSP bloqueando Swagger UI | `Content-Security-Policy` restritivo em `main.py` | Middleware corrigido: `/docs /redoc /openapi.json` não recebem header CSP |
| Container usa imagem antiga após push | Docker cache no ICP | ICP Compose → Editar → Confirmar |
| Aviso `LF will be replaced by CRLF` | Git no Windows converte quebras de linha | Normal — apenas aviso informativo |
| `.venv` apontando para Python errado | `.venv` de outro usuário/máquina | `python -m venv .venv` e recriar o ambiente |

---

## 📋 Checklist Final

| # | Verificação | ✓ |
|---|-------------|---|
| 1 | `requirements.txt` no repositório | ☐ |
| 2 | `Dockerfile` no repositório | ☐ |
| 3 | GitHub Action publica imagem (GHCR) | ☐ |
| 4 | ICP Compose: `docker-compose up successful!` | ☐ |
| 5 | Log: `Application startup complete.` | ☐ |
| 6 | `:8000/health` → `{"status":"ok"}` | ☐ |
| 7 | `:8000/docs` abre sem erro CSP | ☐ |
| 8 | Volume `rde_db` montado em `/data` | ☐ |
| 9 | HTTPS + domínio configurado | ☐ |
| 10 | Frontend na Vercel funcionando | ☐ |
