# Plano de Otimização de Performance e Alta Concorrência — RDE Platform

## 📋 Resumo Executivo
Este documento contém o plano técnico e arquitetural para transformar a **RDE Platform** em um sistema de altíssimo desempenho, escalabilidade e carregamento instantâneo (< 1 segundo) tanto em **Desenvolvimento** quanto em **Produção (Docker / VPS / ICP Panel)**.

---

## 🔍 1. Diagnóstico de Gargalos Atuais

### 1.1 Banco de Dados: SQLite vs. Concorrência Real
- **Problema Atual:** O SQLite opera por bloqueio de arquivo em disco. Quando o Telegram Copier ou múltiplos workers do Uvicorn executam escritas simultâneas, as consultas de leitura (como carregar a Dashboard ou trocar de aba no Sidebar) ficam em fila aguardando liberação do arquivo.
- **Solução:** Migração completa para **PostgreSQL 16 (com `asyncpg`)**.

### 1.2 Bloqueio Síncrono de Corretoras (`/broker/refresh-balance`)
- **Problema Atual:** Ao consultar o saldo, o backend tenta se conectar diretamente na IQ Option via sockets síncronos e `time.sleep(2)`. Isso segura a thread do worker por 3 a 8 segundos. Enquanto o worker está ocupado, qualquer clique no frontend fica travado em fila.
- **Solução:** Desacoplar o saldo — o endpoint responde instantaneamente (< 5ms) com o saldo persistido, enquanto atualizações em tempo real são sincronizadas em background.

### 1.3 Entrega de Chunks do Next.js sem Proxy HTTP/2
- **Problema Atual:** O Uvicorn (servidor Python) entrega scripts estáticos via HTTP/1.1 sequencial na porta `:8000`.
- **Solução:** Proxy Nginx entregando arquivos estáticos via **HTTP/2 multiplexado** com cache imutável (`Cache-Control: public, max-age=31536000, immutable`).

### 1.4 Handshake IPv6 no Telegram
- **Problema Atual:** O Telethon tentava resolver servidores do Telegram por IPv6 antes do IPv4 em containers Linux, gerando atrasos de 30s.
- **Solução:** Forçar `use_ipv6=False` e reaproveitar instâncias do cliente.

---

## 🛠️ 2. Fases de Implementação do Plano

```
[Fase 1: PostgreSQL] ➔ [Fase 2: Backend Assíncrono] ➔ [Fase 3: Nginx HTTP/2] ➔ [Fase 4: Frontend Otimizado]
```

---

### 🐘 Fase 1: Migração para PostgreSQL (Dev & Produção)

#### Por que o PostgreSQL faz toda a diferença?
1. **Concorrência Real (MVCC):** Leituras e escritas ilimitadas em paralelo sem nenhuma trava de arquivo.
2. **Pool de Conexões Assíncrono:** O SQLAlchemy com driver `asyncpg` gerencia pool de 20 a 60 conexões de alto throughput.
3. **Ambiente Idêntico (Dev e Prod):** Elimina divergências entre Windows/Linux e garante paridade de dados.

#### Dependências no `requirements.txt`:
```txt
asyncpg>=0.29.0
psycopg2-binary>=2.9.9
```

#### Configuração no `docker-compose.yml` e `docker-compose.icp.yml`:
```yaml
services:
  postgres:
    image: postgres:16-alpine
    container_name: rde-postgres
    restart: unless-stopped
    environment:
      POSTGRES_USER: rde_user
      POSTGRES_PASSWORD: rde_secure_password
      POSTGRES_DB: rde_platform
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    networks:
      - rde-net

  rde-backend:
    depends_on:
      - postgres
    environment:
      - DATABASE_URL=postgresql+asyncpg://rde_user:rde_secure_password@postgres:5432/rde_platform

volumes:
  postgres_data:
```

---

### ⚡ Fase 2: Desbloqueio do Backend e APIs de Corretora / Telegram

1. **Saldo Imediato e Não-Bloqueante (`src/routes/broker.py`):**
   - Retornar o saldo mais recente salvo no PostgreSQL ou memória cache em **< 5ms**.
   - Atualizar a conexão com a IQ Option / Quotex exclusivamente em tarefas assíncronas de segundo plano.
2. **Otimização do Telegram Client (`src/routes/telegram_auth.py`):**
   - Manter conexões ativas persistentes com `use_ipv6=False` e timeouts de socket em 10s.

---

### ⚡ Fase 3: Proxy Reverso Nginx com HTTP/2 e Cache Imutável

Configuração do Nginx para servir o Next.js estático e repassar a API ao FastAPI:

```nginx
server {
    listen 80;
    listen 443 ssl http2;
    server_name _;

    # Chunks do Next.js: Cache permanente no navegador
    location /_next/static/ {
        alias /app/cliente/frontend/_next/static/;
        expires 365d;
        add_header Cache-Control "public, max-age=31536000, immutable";
        access_log off;
    }

    # Demais arquivos estáticos
    location ~* \.(html|ico|png|jpg|svg|css|js|txt)$ {
        root /app/cliente/frontend;
        expires 1h;
        add_header Cache-Control "no-cache, must-revalidate";
        try_files $uri $uri.html /index.html;
    }

    # API Backend FastAPI
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

### ⚡ Fase 4: Otimização de Polling e Navegação no Frontend

1. **Cache de Estado em Memória (`EstadoContext`):**
   - A navegação entre páginas da Sidebar deve reutilizar o estado em memória, respondendo em **30 a 50ms**.
2. **Debounce e Pooling Inteligente:**
   - Evitar disparos repetidos de `/broker/refresh-balance` e `/dashboard/live` em paralelo ao trocar de rota.

---

## 📊 Matriz Comparativa: Antes vs. Depois

| Métrica / Cenário | Arquitetura Anterior | Nova Arquitetura Proposta |
| :--- | :--- | :--- |
| **Banco de Dados** | SQLite (travamento em escritas) | **PostgreSQL 16 com asyncpg** (MVCC ilimitado) |
| **Clique na Sidebar** | 2 a 8 segundos (fila no worker) | **30 a 50 ms** (SPA em memória + Nginx HTTP/2) |
| **Consulta de Saldo** | Bloqueante (3 a 5s por request) | **Instantâneo (< 5ms)** via DB cache |
| **Telegram Auth / Code** | 30 a 45s (tentativas IPv6) | **1 a 3s** (IPv4 direto + timeouts curtos) |
| **Throughput HTTP** | ~50 req/s | **> 2.500 req/s** |

---

## 📌 Roteiro de Execução Recomendado

1. **Passo 1:** Adicionar `asyncpg` e `psycopg2-binary` no `requirements.txt` e o container `postgres:16-alpine` no Docker Compose.
2. **Passo 2:** Desacoplar a rota de saldo da corretora no backend para responder em <5ms.
3. **Passo 3:** Adicionar a configuração do Nginx para entrega HTTP/2 dos arquivos estáticos.
4. **Passo 4:** Realizar testes de carga e validação da navegação na VPS.
