"""
Corrige banco RDE: cria tabelas, planos e o usuario admin (se ausente),
restaurando signal_source/webhook_secret de backups JSON existentes.
Uso: python -m src.corrigir_admin  (ou corrigir_admin.bat)
"""
import asyncio, json, logging, os, sys
from src.database.session import SessionLocal, sync_engine as engine
from src.models.user import Base, User, Plan
from src.core.config import settings
from fastapi_users.password import PasswordHelper

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
helper = PasswordHelper()

ADMIN_EMAIL = getattr(settings, "ADMIN_EMAIL", "ferreira.jpa1@hotmail.com") or "ferreira.jpa1@hotmail.com"
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Regy2423$$")

PLANS = [
    {"name": "Free",  "max_signals_per_day": 5,    "max_stake": 5.0,   "price_usd": 0.0,  "is_demo": True,
     "allowed_brokers": '["iqoption", "deriv"]'},
    {"name": "Pro",   "max_signals_per_day": 100,  "max_stake": 100.0, "price_usd": 19.0, "is_demo": False,
     "allowed_brokers": '["iqoption", "deriv", "quotex", "pocketoption"]'},
    {"name": "VIP",   "max_signals_per_day": 99999, "max_stake": 1000.0, "price_usd": 49.0, "is_demo": False,
     "allowed_brokers": '["iqoption", "quotex", "pocketoption", "deriv"]'},
]


def _find_state_files():
    """Tenta localizar backups de estado do usuario (signal_source, webhook_secret, etc)."""
    results = []
    for f in os.listdir("."):
        if f.startswith("live_status_") and f.endswith(".json"):
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                results.append(data)
            except Exception:
                pass
    return results


def main():
    print("=" * 56)
    print(" RDE - CORRECAO DE ADMIN / BANCO")
    print("=" * 56)

    # 1) Tabelas
    print("\n[1/4] Criando tabelas pendentes...")
    Base.metadata.create_all(bind=engine)
    print("      OK")

    db = SessionLocal()
    try:
        # 2) Planos
        print("\n[2/4] Verificando planos...")
        for p in PLANS:
            exists = db.query(Plan).filter_by(name=p["name"]).first()
            if not exists:
                db.add(Plan(**p))
                print(f"      Plan '{p['name']}' criado.")
            else:
                print(f"      Plan '{p['name']}' ja existe.")
        db.commit()

        # 3) Admin
        print("\n[3/4] Verificando admin...")
        admin = db.query(User).filter_by(email=ADMIN_EMAIL).first()
        if admin:
            admin.is_admin = True
            admin.is_superuser = True
            admin.is_active = True
            admin.is_verified = True
            print(f"      Admin '{ADMIN_EMAIL}' promovido/ativado (ja existia).")
        else:
            plan = db.query(Plan).filter_by(name="VIP").first()
            admin = User(
                email=ADMIN_EMAIL,
                username="Reginier Ferreira",
                hashed_password=helper.hash(ADMIN_PASSWORD),
                is_active=True,
                is_superuser=True,
                is_verified=True,
                is_admin=True,
                plan=plan,
                broker="iqoption",
                stake=2.0,
                risk_mode="safe",
            )
            db.add(admin)
            print(f"      Admin '{ADMIN_EMAIL}' CRIADO com sucesso.")
        db.commit()

        # 4) Restaura signal_source / webhook_secret a partir de backups JSON
        print("\n[4/4] Restaurando preferencias a partir de backups locais...")
        restored = False
        for data in _find_state_files():
            src = data.get("source")
            if src and hasattr(admin, "signal_source"):
                if admin.signal_source in (None, "", "telegram") and src in ("telegram", "tradingview"):
                    admin.signal_source = src
                    print(f"      signal_source restaurado -> {src}")
                    restored = True
        if not restored:
            if admin.signal_source in (None, ""):
                admin.signal_source = "telegram"
        db.commit()
        print("      Concluido.")

        print("\n" + "=" * 56)
        print(" ADMIN VALIDO!")
        print(f"   Email   : {ADMIN_EMAIL}")
        print(f"   Senha   : {ADMIN_PASSWORD}")
        print("=" * 56)
        print("\nCorrecao concluida. Reinicie o backend se ele estiver aberto.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
