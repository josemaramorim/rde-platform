"""Base interface that all broker adapters must implement."""


class BaseBroker:

    def connect(self):
        """Establish connection/authentication with the broker."""
        raise NotImplementedError

    def send_order(self, symbol: str, stake: float, direction: str, duration: int = 1) -> dict:
        """
        Place a trade order.
        direction: 'CALL' / 'PUT' (Deriv) or 'call' / 'put' (IQ Option)
        duration: in minutes (1 for M1, 5 for M5, etc.)
        Returns a dict with at minimum {'status': ..., 'result': ...}
        """
        raise NotImplementedError

    def get_balance(self) -> float:
        """Fetch current account balance."""
        raise NotImplementedError

    def disconnect(self):
        """Cleanly close the connection (optional)."""
        pass
