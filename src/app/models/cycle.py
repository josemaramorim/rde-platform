from sqlalchemy import Column, Integer, DECIMAL, ForeignKey, DateTime
from sqlalchemy.sql import func
from src.app.database import Base


class Cycle(Base):
    __tablename__ = "cycles"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    max_level = Column(Integer, default=6)
    exposure_percent = Column(DECIMAL(5, 2))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
