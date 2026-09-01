"""
Seed script – creates or UPDATES Free / Pro / VIP plans.
Run: python -m src.seed_plans
"""
from src.database.session import SessionLocal, sync_engine as engine
from src.models.user import Base, Plan
from src.models.broker import BrokerSetting

# Ensure tables exist (sync)
Base.metadata.create_all(bind=engine)

# Regras de corretoras por plano
PLAN_BROKERS = {
    "Free":  '["iqoption"]',
    "Pro":   '["iqoption", "deriv"]',
    "VIP":   '["iqoption", "deriv", "quotex", "pocketoption"]',
}


def seed():
    db = SessionLocal()
    try:
        plans = [
            {"name": "Free",  "max_signals_per_day": 5,
                "max_stake": 5.0,    "price_usd": 0.0,  "is_demo": True,
                "allowed_brokers": PLAN_BROKERS["Free"]},
            {"name": "Pro",   "max_signals_per_day": 100,
                "max_stake": 100.0,  "price_usd": 19.0, "is_demo": False,
                "allowed_brokers": PLAN_BROKERS["Pro"]},
            {"name": "VIP",   "max_signals_per_day": 99999,
                "max_stake": 1000.0, "price_usd": 49.0, "is_demo": False,
                "allowed_brokers": PLAN_BROKERS["VIP"]},
        ]

        for p in plans:
            existing = db.query(Plan).filter_by(name=p["name"]).first()
            if not existing:
                db.add(Plan(**p))
                print(f"  ✓ Plan '{p['name']}' created.")
            else:
                # Atualiza allowed_brokers mesmo se o plano já existir
                existing.allowed_brokers = p["allowed_brokers"]
                print(f"  ↺ Plan '{p['name']}' updated → brokers: {p['allowed_brokers']}")

        db.commit()
        print("\nSeed complete.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
