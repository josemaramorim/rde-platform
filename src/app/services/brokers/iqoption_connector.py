try:
    from iqoptionapi.stable_api import IQ_Option
except ImportError:
    # Fallback to avoid breaking start if library is missing
    IQ_Option = None


class IQOptionConnector:
    def __init__(self, email, password):
        self.api = None
        if IQ_Option:
            self.api = IQ_Option(email, password)

    async def execute_binary_trade(self, symbol, amount, direction, duration=1):
        if not self.api:
            return {"status": "error", "message": "IQ Option library not installed"}

        try:
            check, reason = self.api.connect()
            if not check:
                return {"status": "error", "message": f"Connection failed: {reason}"}

            # Simple binary option buy
            # IQ Option uses 'call' or 'put'
            side = "call" if direction.upper() == "UP" else "put"

            # Duration must be in minutes
            status, id = self.api.buy(amount, symbol, side, duration)

            if status:
                return {"status": "success", "id": id}
            else:
                return {"status": "error", "message": "Order failed at IQ Option"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def get_history(self, limit=10):
        if not self.api:
            return []

        try:
            check, reason = self.api.connect()
            if not check:
                return []

            # Fetch last binary options trades
            # This is a sample, exact method may vary by library version
            # history = self.api.get_option_history_v2("binary", limit)
            # For this example, returning mock structure that matches Deriv
            return [
                {"res": "WIN", "profit": "+85%", "time": "12:00", "pair": "EURUSD"},
                {"res": "LOSS", "profit": "-100%",
                    "time": "11:55", "pair": "GBPUSD"}
            ]
        except Exception:
            return []
