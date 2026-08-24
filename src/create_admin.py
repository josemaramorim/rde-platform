"""
Cria ou promove um usuario a administrador.
Uso: python -m src.create_admin
"""
from __future__ import annotations

import asyncio
import logging
import getpass
from src.database.session import AsyncSessionLocal, engine  # Importado o 'engine' correto aqui
from src.models.user import User, Plan
from sqlalchemy import select
from fastapi_users.password import PasswordHelper

# Configuração básica de log para exibir mensagens no terminal
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
helper = PasswordHelper()
logger = logging.getLogger("rde")


async def create_admin():
    print("\n====================================")
    print(" 👑 RDE — CONFIGURAR ADMINISTRADOR")
    print("====================================\n")

    email    = input("Digite o E-mail do Admin (ex: ferreira.jpa1@hotmail.com): ").strip()
    username = input("Digite o Nome do Admin (ex: Reginier Ferreira): ").strip()
    password = getpass.getpass("Digite a Senha (mínimo 8 caracteres): ")
    confirm  = getpass.getpass("Confirme a Senha: ")

    if not email or not username:
        logger.error("E-mail e Nome de usuário são obrigatórios.")
        return

    if password != confirm:
        logger.error("As senhas não coincidem.")
        return

    if len(password) < 8:
        logger.error("A senha deve ter pelo menos 8 caracteres.")
        return

    # ── CRIAÇÃO AUTOMÁTICA DAS TABELAS ────────────────────────────────────────
    logger.info("Verificando e criando tabelas pendentes no banco de dados...")
    
    try:
        from src.database.base import Base
    except ImportError:
        from src.database.base_class import Base

    # Usando o motor assíncrono nativo do seu projeto para gerar as tabelas
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Tabelas sincronizadas com sucesso!")
    # ──────────────────────────────────────────────────────────────────────────

    async with AsyncSessionLocal() as db:
        # Verificar se ja existe
        result = await db.execute(select(User).where(User.email == email)) # type: ignore
        user   = result.scalar_one_or_none()

        if user:
            user.is_superuser = True
            user.is_admin     = True
            user.is_active    = True
            await db.commit()
            logger.info(f"Usuário '{email}' promovido a administrador com sucesso no DB!")
        else:
            # Buscar plano VIP para o admin
            plan_result = await db.execute(select(Plan).where(Plan.name == "VIP"))
            plan = plan_result.scalar_one_or_none()

            new_user = User(
                email        = email,
                username     = username,
                hashed_password = helper.hash(password),
                is_active    = True,
                is_superuser = True,
                is_verified  = True,
                is_admin     = True,
                plan         = plan,
                broker       = "iqoption",  
                stake        = 2.0,
                risk_mode    = "safe",
            )
            db.add(new_user)
            await db.commit()
            
            print("\n" + "=" * 40)
            print("✅ Admin criado com sucesso!")
            print(f"   E-mail  : {email}")
            print(f"   Username: {username}")
            print(f"   Plano   : VIP")
            print("=" * 40 + "\n")


if __name__ == "__main__":
    asyncio.run(create_admin())