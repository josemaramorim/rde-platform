# Guia Operacional: PostgreSQL & Usuários Administradores — RDE Platform

## 📋 Sumário
1. [Visão Geral e Arquitetura do Banco de Dados](#1-visão-geral-e-arquitetura)
2. [Credenciais Padrão do PostgreSQL](#2-credenciais-padrão-do-postgresql)
3. [Como Inicializar o PostgreSQL no Docker](#3-como-inicializar-o-postgresql-no-docker)
4. [Usuário Administrador Inicial (Seed Automático)](#4-usuário-administrador-inicial-seed-automático)
5. [Como Criar ou Promover um Administrador Manualmente](#5-como-criar-ou-promover-um-administrador-manualmente)
6. [Planos Padrão do Sistema](#6-planos-padrão-do-sistema)
7. [Comandos de Manutenção, Backup e Acesso ao Banco](#7-comandos-de-manutenção-backup-e-acesso-ao-banco)
8. [Variáveis de Ambiente Recomendadas](#8-variáveis-de-ambiente-recomendadas)

---

## 1. Visão Geral e Arquitetura

A **RDE Platform** utiliza o **PostgreSQL 16** como banco de dados principal de produção e desenvolvimento, operando com conexões assíncronas de altíssimo desempenho via driver `asyncpg` e suporte a múltiplos workers em paralelo sem concorrência ou travamento de arquivo.

- **Container do Banco:** `rde-postgres` (imagem: `postgres:16-alpine`)
- **Container da Aplicação:** `rde-platform`
- **Volume de Dados Persistente:** `postgres_data` (armazenado fisicamente no disco do host, garantindo que nada seja perdido em reinicializações ou novos deploys).

---

## 2. Credenciais Padrão do PostgreSQL

As credenciais abaixo são configuradas por padrão no `docker-compose.yml` e `docker-compose.icp.yml`:

| Parâmetro | Valor Padrão | Descrição |
| :--- | :--- | :--- |
| **Host Interno** | `postgres` | Nome do serviço na rede interna do Docker (`rde-net`) |
| **Porta** | `5432` | Porta padrão do PostgreSQL |
| **Database** | `rde_platform` | Nome do banco de dados principal |
| **Usuário** | `rde_user` | Usuário proprietário do banco |
| **Senha** | `rde_pass_2026` | Senha padrão do usuário |
| **String de Conexão (Async)** | `postgresql+asyncpg://rde_user:rde_pass_2026@postgres:5432/rde_platform` | Usada pelo FastAPI |
| **String de Conexão (Sync)** | `postgresql://rde_user:rde_pass_2026@postgres:5432/rde_platform` | Usada por scripts e migrações |

---

## 3. Como Inicializar o PostgreSQL no Docker

### Em Produção (VPS):
```bash
# 1. Baixar a imagem mais recente compilada pelo GitHub Actions
docker compose pull

# 2. Iniciar os containers (PostgreSQL + Backend)
docker compose up -d

# 3. Verificar o status dos containers
docker compose ps
```

### Em Desenvolvimento Local:
```powershell
docker compose -f docker-compose.yml up -d
```

---

## 4. Usuário Administrador Inicial (Seed Automático)

No **primeiro boot** da aplicação com o PostgreSQL vazio, o backend executa automaticamente o *Seed Inicial* e cria o seguinte usuário administrador:

- **E-mail:** `admin@rde-platform.com`
- **Senha Inicial:** `admin123456`
- **Nome:** `Administrador`
- **Nível de Acesso:** `Superuser / Admin (VIP)`
- **Permissões:** Acesso completo à aba `/admin`, gerenciamento de tokens, status dos robôs e configurações globais.

> 🔒 **Recomendação:** Após o primeiro login, você pode alterar a senha na aba de Perfil (`/perfil`) ou criar o seu próprio administrador pelo terminal conforme a Seção 5.

---

## 5. Como Criar ou Promover um Administrador Manualmente

Você pode criar novos administradores ou promover um usuário existente a qualquer momento executando o script interativo dentro do container:

```bash
docker exec -it rde-platform python -m src.create_admin
```

O terminal solicitará interativamente:
1. **E-mail do Admin** (Ex: `seuemail@gmail.com`)
2. **Nome do Usuário** (Ex: `Josemar Amorim`)
3. **Senha (mínimo 8 caracteres)**
4. **Confirmação de Senha**

O script cria o usuário com senha criptografada em *bcrypt*, atribui o plano **VIP** e ativa as flags de administrador no PostgreSQL instantaneamente.

---

## 6. Planos Padrão do Sistema

O sistema cria automaticamente os 3 planos padrão no primeiro boot:

| Plano | Limite de Sinais / Dia | Entrada Máxima ($) | Corretoras Permitidas | Modo Padrão |
| :--- | :---: | :---: | :--- | :---: |
| **Free** | 5 sinais | $ 5.00 | IQ Option, Deriv | Demo |
| **Pro** | 100 sinais | $ 100.00 | IQ Option, Deriv | Real / Demo |
| **VIP** | Ilimitado (99.999) | $ 1.000.00 | IQ Option, Deriv | Real / Demo |

---

## 7. Comandos de Manutenção, Backup e Acesso ao Banco

### 7.1 Acessar o Terminal do PostgreSQL (psql):
```bash
docker exec -it rde-postgres psql -U rde_user -d rde_platform
```
*Comandos úteis dentro do psql:*
- `\dt` — Lista todas as tabelas.
- `SELECT id, email, is_admin, is_active FROM users;` — Lista todos os usuários.
- `\q` — Sair do psql.

### 7.2 Fazer Backup Completo do Banco (Dump SQL):
```bash
docker exec -t rde-postgres pg_dump -U rde_user rde_platform > backup_rde_$(date +%Y%m%d_%H%M%S).sql
```

### 7.3 Restaurar Backup a Partir de um Arquivo SQL:
```bash
cat backup_rde.sql | docker exec -i rde-postgres psql -U rde_user -d rde_platform
```

---

## 8. Variáveis de Ambiente Recomendadas

Se desejar alterar as credenciais padrão do banco ou do admin no arquivo `.env` ou `icontainer.env`:

```env
# Configurações do PostgreSQL
POSTGRES_USER=rde_user
POSTGRES_PASSWORD=rde_pass_2026
POSTGRES_DB=rde_platform
DATABASE_URL=postgresql+asyncpg://rde_user:rde_pass_2026@postgres:5432/rde_platform

# Configurações do Admin Inicial
ADMIN_EMAIL=admin@rde-platform.com
ADMIN_PASSWORD=admin123456

# Configurações do Telegram
TELEGRAM_CHAT_ID=-1001804981654
TELEGRAM_GROUP_NAME=R&DE🇧🇷
TELEGRAM_BOT_TOKEN=7533153324:AAFnjAwlQcLQfJeSFNOPeg0iVI7F97LDzzI
```
