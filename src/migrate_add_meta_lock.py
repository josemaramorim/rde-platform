"""
Migration: add columns meta_hit_today, meta_hit_date, auto_lock_meta to users table.
Run once: python -m src.migrate_add_meta_lock
"""
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("migration")

def run_migration():
    from sqlalchemy import inspect, text
    from src.database.session import sync_engine

    inspector = inspect(sync_engine)
    columns = [c["name"] for c in inspector.get_columns("users")]

    with sync_engine.connect() as conn:
        if "meta_hit_today" not in columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN meta_hit_today BOOLEAN DEFAULT 0"))
            logger.info("+ meta_hit_today")
        if "meta_hit_date" not in columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN meta_hit_date VARCHAR(10)"))
            logger.info("+ meta_hit_date")
        if "auto_lock_meta" not in columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN auto_lock_meta BOOLEAN DEFAULT 0"))
            logger.info("+ auto_lock_meta")
        conn.commit()

    logger.info("Migracao concluida.")

if __name__ == "__main__":
    run_migration()
