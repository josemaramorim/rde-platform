"""
Migration: add per-broker risk config columns to broker_settings table.
Copies existing user-level values to each user's active broker setting.
Run once: python -m src.migrate_add_broker_risk_config
"""
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("migration")

def run_migration():
    from sqlalchemy import inspect, text
    from src.database.session import sync_engine

    inspector = inspect(sync_engine)
    columns = [c["name"] for c in inspector.get_columns("broker_settings")]

    with sync_engine.connect() as conn:
        if "stop_loss_pct" not in columns:
            conn.execute(text("ALTER TABLE broker_settings ADD COLUMN stop_loss_pct FLOAT DEFAULT 5.0"))
            logger.info("+ stop_loss_pct")
        if "daily_meta_pct" not in columns:
            conn.execute(text("ALTER TABLE broker_settings ADD COLUMN daily_meta_pct FLOAT DEFAULT 3.0"))
            logger.info("+ daily_meta_pct")
        if "stake" not in columns:
            conn.execute(text("ALTER TABLE broker_settings ADD COLUMN stake FLOAT DEFAULT 1.0"))
            logger.info("+ stake")
        if "auto_lock_meta" not in columns:
            conn.execute(text("ALTER TABLE broker_settings ADD COLUMN auto_lock_meta BOOLEAN DEFAULT 0"))
            logger.info("+ auto_lock_meta")
        if "meta_hit_today" not in columns:
            conn.execute(text("ALTER TABLE broker_settings ADD COLUMN meta_hit_today BOOLEAN DEFAULT 0"))
            logger.info("+ meta_hit_today")
        if "meta_hit_date" not in columns:
            conn.execute(text("ALTER TABLE broker_settings ADD COLUMN meta_hit_date VARCHAR(20)"))
            logger.info("+ meta_hit_date")
        conn.commit()

    # Copy existing user-level values to each user's active broker setting
    with sync_engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT bs.id, u.stop_loss_pct, u.daily_meta_pct, u.stake,
                       u.auto_lock_meta, u.meta_hit_today, u.meta_hit_date
                FROM broker_settings bs
                JOIN users u ON u.id = bs.user_id
                WHERE bs.is_active = 1
            """)
        ).fetchall()
        updated = 0
        for row in rows:
            conn.execute(
                text("""
                    UPDATE broker_settings SET
                        stop_loss_pct = :sl,
                        daily_meta_pct = :dm,
                        stake = :st,
                        auto_lock_meta = :alm,
                        meta_hit_today = :mht,
                        meta_hit_date = :mhd
                    WHERE id = :bid
                """),
                {
                    "bid": row[0],
                    "sl": row[1] or 5.0,
                    "dm": row[2] or 3.0,
                    "st": row[3] or 1.0,
                    "alm": row[4] or False,
                    "mht": row[5] or False,
                    "mhd": row[6],
                }
            )
            updated += 1
        conn.commit()
        logger.info(f"Copiados valores de usuario para {updated} broker(s) ativo(s).")

    logger.info("Migracao concluida.")

if __name__ == "__main__":
    run_migration()
