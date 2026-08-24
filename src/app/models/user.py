# Re-export canonical models to avoid duplicate mapper conflict
from src.models.user import User, Plan

__all__ = ["User", "Plan"]
