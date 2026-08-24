from sqlalchemy import Column, Integer, String, DECIMAL, ForeignKey, DateTime
from sqlalchemy.sql import func
from src.app.database import Base


class Operation(Base):
    __tablename__ = "operations"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    result = Column(String(10))
    profit = Column(DECIMAL(10, 2))
    sequence = Column(Integer)
    cycle_level = Column(Integer)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
