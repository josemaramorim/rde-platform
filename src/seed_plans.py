"""
Seed script – creates default Free / Pro / VIP plans.
Run once: python -m src.seed_plans
"""
from src.database.session import SessionLocal, sync_engine as engine
from src.models.user import Base, Plan
from src.models.broker import BrokerSetting

# Ensure tables exist (sync)
Base.metadata.create_all(bind=engine)


def seed():
    db = SessionLocal()
    try:
        plans = [
            {"name": "Free",  "max_signals_per_day": 5,
                "max_stake": 5.0,    "price_usd": 0.0,  "is_demo": True,
                "allowed_brokers": '["iqoption", "deriv"]'},
            {"name": "Pro",   "max_signals_per_day": 100,
                "max_stake": 100.0,  "price_usd": 19.0, "is_demo": False,
                "allowed_brokers": '["iqoption", "deriv"]'},
            {"name": "VIP",   "max_signals_per_day": 99999,
                "max_stake": 1000.0, "price_usd": 49.0, "is_demo": False,
                "allowed_brokers": '["iqoption", "deriv"]'},
        ]

        for p in plans:
            exists = db.query(Plan).filter_by(name=p["name"]).first()
            if not exists:
                db.add(Plan(**p))
                print(f"  ✓ Plan '{p['name']}' created.")
            else:
                print(f"  — Plan '{p['name']}' already exists, skipping.")

        db.commit()
        print("\nSeed complete.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
