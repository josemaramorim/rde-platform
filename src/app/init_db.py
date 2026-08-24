from src.app.database import engine, Base
from src.app.models.user import User, Plan
from src.app.models.operation import Operation
from src.app.models.cycle import Cycle
from src.app.models.subscription import Subscription
from src.app.models.broker import BrokerSetting


def init_db():
    logger.info("Initializing database...")
    Base.metadata.create_all(bind=engine)
    logger.info("Database initialized successfully.")


if __name__ == "__main__":
    init_db()
