from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from src.core.config import settings

# Since we might use async or sync, let's keep it simple for preview
# The provided SQL uses psycopg2-binary so we use sync engine for now
DATABASE_URL = settings.DATABASE_URL.replace(
    "asyncpg", "psycopg2") if settings.DATABASE_URL else "sqlite:///./test.db"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
