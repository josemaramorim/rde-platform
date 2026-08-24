import json
import asyncio
import websockets
from src.app.services.encryption_service import encryption_service


class DerivConnector:
    def __init__(self, api_token, app_id="019dfcf3-9df3-71f4-aef1-689e60afe368"):
        self.api_token = api_token
        self.url = f"wss://ws.derivws.com/websockets/v3?app_id={app_id}"

    async def execute_trade(self, symbol, amount, direction, duration=1, duration_unit="m"):
        try:
            async with websockets.connect(self.url) as ws:
                # 1. Authorize
                await ws.send(json.dumps({"authorize": self.api_token}))
                auth_res = json.loads(await ws.recv())

                if "error" in auth_res:
                    return {"status": "error", "message": auth_res["error"]["message"]}

                # 2. Place Order
                contract_type = "CALL" if direction.upper() == "UP" else "PUT"
                trade_params = {
                    "buy": 1,
                    "price": float(amount),
                    "parameters": {
                        "amount": float(amount),
                        "basis": "stake",
                        "contract_type": contract_type,
                        "currency": "USD",
                        "duration": int(duration),
                        "duration_unit": duration_unit,
                        "underlying_symbol": symbol
                    }
                }
                await ws.send(json.dumps(trade_params))
                res = json.loads(await ws.recv())

                if "error" in res:
                    return {"status": "error", "message": res["error"]["message"]}

                return {
                    "status": "success",
                    "id": res["buy"]["contract_id"],
                    "entry_price": float(res["buy"]["buy_price"])
                }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def get_history(self, limit=10):
        try:
            async with websockets.connect(self.url) as ws:
                await ws.send(json.dumps({"authorize": self.api_token}))
                auth_res = json.loads(await ws.recv())
                if "error" in auth_res:
                    return []

                await ws.send(json.dumps({
                    "profit_table": 1,
                    "description": 1,
                    "limit": limit,
                    "sort": "DESC"
                }))
                res = json.loads(await ws.recv())

                if "error" in res:
                    return []

                history = []
                for transaction in res["profit_table"]["transactions"]:
                    history.append({
                        "res": "WIN" if transaction["sell_price"] > transaction["buy_price"] else "LOSS",
                        "profit": f"{round(((transaction['sell_price'] - transaction['buy_price']) / transaction['buy_price']) * 100, 2)}%",
                        "time": transaction["purchase_time"],
                        "pair": transaction["display_name"]
                    })
                return history
        except Exception:
            return []
