"""
Setup broker credentials for the admin user in the database.

This script:
  1. Finds or creates the admin user (ferreira.jpa1@hotmail.com)
  2. Inserts/updates BrokerSetting entries for IQ Option and Deriv
  3. Prefills required database structural fields like broker_type
  4. Sets IQ Option as the active broker by default

Usage: python -m src.setup_brokers
"""
import asyncio
import logging
import os
import uuid
from dotenv import load_dotenv
from sqlalchemy import select
from src.core.config import settings

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rde-setup")

ADMIN_EMAIL = settings.ADMIN_EMAIL

# ── Broker Credentials (Alinhado 100% com o Schema do Banco de Dados) ──────────
BROKERS = [
    {
        "broker_name": "iqoption",
        "broker_type": "iqoption",  
        "api_token": None,
        "is_active": True,
        "is_primary": True,
    },
]


async def setup_brokers():
    from src.database.session import AsyncSessionLocal
    from src.models.user import User
    from src.models.broker import BrokerSetting
    from src.core.security import encryption_service

    async with AsyncSessionLocal() as db:
        # 1. Find admin user
        result = await db.execute(select(User).where(User.email == ADMIN_EMAIL))
        user = result.scalar_one_or_none()

        if not user:
            logger.error(
                f"❌ Usuário '{ADMIN_EMAIL}' não encontrado no banco.\n"
                "   Rode primeiro: python -m src.create_admin"
            )
            return

        logger.info(f"✅ Usuário encontrado: {user.email} (ID: {user.id})")

        # 2. Upsert broker settings
        for config in BROKERS:
            broker_name = config["broker_name"]

            # Check if exists
            existing_result = await db.execute(
                select(BrokerSetting).where(
                    BrokerSetting.user_id == user.id,
                    BrokerSetting.broker_name == broker_name,
                )
            )
            existing = existing_result.scalar_one_or_none()

            # Encrypt sensitive data (apenas se houver token)
            enc_token = (
                encryption_service.encrypt(config["api_token"])
                if config["api_token"]
                else None
            )

            if existing:
                existing.api_token = enc_token
                existing.broker_type = config["broker_type"]
                existing.is_active = config["is_active"]
                existing.is_primary = config["is_primary"]
                logger.info(f"  🔄 Atualizado no DB: {broker_name}")
            else:
                # 💡 CORREÇÃO AQUI: Passando o objeto UUID nativo em vez de string .hex
                obj_id = uuid.uuid4()
                
                new_setting = BrokerSetting(
                    id=obj_id,
                    user_id=user.id,
                    broker_name=broker_name,
                    broker_type=config["broker_type"],
                    api_token=enc_token,
                    is_active=config["is_active"],
                    is_primary=config["is_primary"],
                    status="DISCONNECTED",             
                    latency_protection=0,
                    auto_stop_on_loss=1,
                    total_trades=0,
                    total_wins=0,
                    total_losses=0,
                    total_profit=0.0,
                    today_trades=0,
                    today_profit=0.0
                )
                db.add(new_setting)
                logger.info(f"  ✅ Criado no DB: {broker_name}")

        # 3. Update user's default active broker field to IQ Option
        user.broker = "iqoption"
        user.risk_mode = "safe"
        user.is_active_trading = True
        user.trading_enabled = True

        # Sincroniza as credenciais brutas da IQ direto no User
        if os.getenv("IQ_PASSWORD"):
            user.iq_password = encryption_service.encrypt(os.getenv("IQ_PASSWORD"))
        if os.getenv("IQ_EMAIL"):
            user.iq_email = os.getenv("IQ_EMAIL")

        await db.commit()

        # 4. Summary
        print("\n" + "=" * 60)
        print("📋 Resumo das configurações de corretoras:")
        print("=" * 60)
        for config in BROKERS:
            active = "✅ ATIVO" if config["is_active"] else "⬜ Inativo"
            has_token = "✓" if config["api_token"] else "✗"
            print(
                f"  {config['broker_name'].upper():15s} | "
                f"{active:12s} | "
                f"Token/SSID salvo: {has_token}"
            )
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(setup_brokers())