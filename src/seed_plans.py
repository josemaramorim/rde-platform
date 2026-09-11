"""
Seed script – creates or UPDATES Free / Pro / VIP plans.
Run: python -m src.seed_plans
"""
from src.database.session import SessionLocal, sync_engine as engine
from src.models.user import Base, Plan
from src.models.broker import BrokerSetting
from src.plans_catalog import PLAN_CATALOG, plan_seed_kwargs

# Ensure tables exist (sync)
Base.metadata.create_all(bind=engine)


def seed():
    db = SessionLocal()
    try:
        plans = [plan_seed_kwargs(name) for name in PLAN_CATALOG]

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
