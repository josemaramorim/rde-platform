from fastapi import APIRouter
from src.app.services.mock_risk_engine import MockRiskEngine

router = APIRouter()
engine = MockRiskEngine()


@router.get("/status")
async def get_status():
    stats = engine.generate_operation()
    return {
        "status": "OPERANDO",
        "profit_today": f"+{stats['daily_profit']}%",
        "drawdown": f"-{stats['drawdown']}%",
        "sequence": "L" * stats["sequence"] + "W",
        "cycle": stats["cycle_level"],
        "exposure": "Low"
    }


@router.get("/operations")
async def get_operations():
    return [
        {"res": "WIN", "profit": "+2.3%", "time": "12:05", "pair": "EUR/USD"},
        {"res": "LOSS", "profit": "-1.1%", "time": "11:58", "pair": "GBP/JPY"},
        {"res": "LOSS", "profit": "-2.2%", "time": "11:45", "pair": "BTC/USDT"},
    ]
