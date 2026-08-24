"""
Migration: add destinatario column to token_licencas table.
Run once: python -m src.migrate_add_destinatario
"""
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("migration")

def run_migration():
    from sqlalchemy import inspect, text
    from src.database.session import sync_engine

    inspector = inspect(sync_engine)
    columns = [c["name"] for c in inspector.get_columns("token_licencas")]

    with sync_engine.connect() as conn:
        if "destinatario" not in columns:
            conn.execute(text("ALTER TABLE token_licencas ADD COLUMN destinatario VARCHAR(255)"))
            logger.info("+ destinatario (token_licencas)")
        conn.commit()

    logger.info("Migracao concluida.")

if __name__ == "__main__":
    run_migration()
