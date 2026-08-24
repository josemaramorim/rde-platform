import asyncio
import os
import sys
from logging.config import fileConfig

from alembic import context # type: ignore
from sqlalchemy.ext.asyncio import create_async_engine

# 1. Força o carregamento do arquivo .env antes de importar as configurações do app
from dotenv import load_dotenv
# Encontra o arquivo .env voltando uma pasta a partir da pasta /alembic
dotenv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
load_dotenv(dotenv_path)

# Adiciona a raiz do projeto ao path do sistema
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.config import settings
from src.models.user import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Garante que usaremos a URL vinda do arquivo .env configurado no sistema
database_url = settings.DATABASE_URL
config.set_main_option("sqlalchemy.url", database_url)


def run_migrations_offline() -> None:
    """Executa migrações no modo 'offline'."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    """Função síncrona auxiliar executada dentro do contexto assíncrono."""
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Executa migrações no modo 'online' usando suporte assíncrono nativo."""
    # Cria o engine assíncrono diretamente com a URL do projeto
    connectable = create_async_engine(
        config.get_main_option("sqlalchemy.url"),
        poolclass=None,
    )

    async with connectable.connect() as connection:
        # Executa o mapeamento síncrono do Alembic com segurança
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    # Gerencia o loop de eventos assíncronos de forma limpa
    asyncio.run(run_migrations_online())