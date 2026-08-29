# 🚀 RDE Platform — Passo a Passo para Deploy no Painel iCP (PostgreSQL)

Este documento contém a configuração pronta e testada para criar o ambiente do **zero** no painel **iCP** com banco de dados **PostgreSQL**.

---

## 📋 1. Código para o Editor do Docker Compose

No painel iCP:
1. Acesse **Aplicações** ➔ **Container** ➔ aba **Compose**.
2. Clique em **Criar** (ou *Novo Projeto Compose*).
3. Nomeie o projeto/pasta como: `rde-platform`.
4. Cole o conteúdo abaixo no editor do Compose:

```yaml
services:
  postgres:
    image: postgres:16-alpine
    container_name: rde-postgres
    restart: unless-stopped
    environment:
      POSTGRES_USER: rde_user
      POSTGRES_PASSWORD: rde_pass_2026
      POSTGRES_DB: rde_platform
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    networks:
      - rde-net
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U rde_user -d rde_platform"]
      interval: 5s
      timeout: 5s
      retries: 5

  rde-platform:
    image: ghcr.io/josemaramorim/rde-platform:latest
    container_name: rde-platform
    restart: unless-stopped
    depends_on:
      postgres:
        condition: service_healthy
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql+asyncpg://rde_user:rde_pass_2026@postgres:5432/rde_platform
      - ADMIN_EMAIL=admin@rde-platform.com
      - ADMIN_PASSWORD=admin123456
    networks:
      - rde-net

volumes:
  postgres_data:

networks:
  rde-net:
    driver: bridge
```

---

## ⚙️ 2. Conteúdo para o Campo de Variáveis de Ambiente

No painel iCP, cole o bloco abaixo no campo **Ambiente / Variáveis de Ambiente**:

```env
ENVIRONMENT=production
APP_NAME=RDE Platform
RDE_PROFILE=admin
SECRET_KEY=35a29d88a02fb4f96a05636cea3f65e11ae015ebf0dba10a7ac298140729a39d
ENCRYPTION_KEY=35a29d88a02fb4f96a05636cea3f65e11ae015ebf0dba10a7ac298140729a39d
DATABASE_URL=postgresql+asyncpg://rde_user:rde_pass_2026@postgres:5432/rde_platform
ADMIN_EMAIL=admin@rde-platform.com
ADMIN_PASSWORD=admin123456
TELEGRAM_BOT_TOKEN=7533153324:AAFnjAwlQcLQfJeSFNOPeg0iVI7F97LDzzI
TELEGRAM_CHAT_ID=-1001804981654
TELEGRAM_GROUP_NAME=R&DE🇧🇷
FRONTEND_URL=http://localhost:3000
REDIS_URL=redis://localhost:6379/0
RATE_LIMIT_ENABLED=False
```

---

## 🚀 3. Execução e Validação

1. Clique em **Salvar e Executar / Up** no iCP.
2. Aguarde o download dos containers (`~1 a 2 minutos`).
3. Abra o **Terminal / Exec** do container `rde-platform` e execute:
   ```bash
   python -c "from src.database.session import engine; print(engine.dialect.name)"
   ```
   **Resultado Esperado**: `postgresql`

---

## 🔑 Credenciais Iniciais de Administrador
* **E-mail:** `admin@rde-platform.com`
* **Senha:** `admin123456`
* **Plano:** `VIP` (Licença Ativa Vitalícia)
