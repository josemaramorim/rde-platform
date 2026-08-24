import asyncio
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from src.app.services.mock_risk_engine import MockRiskEngine

router = APIRouter()
engine = MockRiskEngine()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            # Generate a "trade" every 30 seconds
            stats = engine.generate_operation()
            await websocket.send_text(json.dumps(stats))
            await asyncio.sleep(30)
    except WebSocketDisconnect:
        print("Client disconnected")
