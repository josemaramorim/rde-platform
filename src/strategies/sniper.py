import math
import logging
from typing import Optional

logger = logging.getLogger("rde")


class RDESniperStrategy:
    def __init__(self, bb_period=20, bb_dev=2.5, rsi_period=4, atr_period=14, atr_mult=2.0):
        self.bb_period = bb_period
        self.bb_dev = bb_dev
        self.rsi_period = rsi_period
        self.atr_period = atr_period
        self.atr_mult = atr_mult
        self._atr_cache = {}

    def calculate_sma(self, prices, period):
        if len(prices) < period:
            return None
        return sum(prices[-period:]) / period

    def calculate_bollinger_bands(self, prices):
        if len(prices) < self.bb_period:
            return None, None, None
        period_prices = prices[-self.bb_period:]
        sma = sum(period_prices) / self.bb_period
        variance = sum((p - sma) ** 2 for p in period_prices) / self.bb_period
        std_dev = math.sqrt(variance)
        upper_band = sma + (std_dev * self.bb_dev)
        lower_band = sma - (std_dev * self.bb_dev)
        return upper_band, sma, lower_band

    def calculate_rsi(self, prices):
        if len(prices) < self.rsi_period + 1:
            return None
        gains = []
        losses = []
        for i in range(1, len(prices)):
            change = prices[i] - prices[i-1]
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))
        avg_gain = sum(gains[-self.rsi_period:]) / self.rsi_period
        avg_loss = sum(losses[-self.rsi_period:]) / self.rsi_period
        if avg_loss == 0:
            return 100
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def calculate_atr(self, candles) -> Optional[float]:
        if len(candles) < self.atr_period + 1:
            return None
        tr_values = []
        for i in range(1, len(candles)):
            high = candles[i].get("high", candles[i].get("max", 0))
            low = candles[i].get("low", candles[i].get("min", 0))
            prev_close = candles[i-1].get("close", candles[i-1].get("close", 0))
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            tr_values.append(tr)
        atr = sum(tr_values[-self.atr_period:]) / self.atr_period
        return atr

    def get_volatility_state(self, candles) -> dict:
        atr = self.calculate_atr(candles)
        if atr is None:
            return {"volatile": False, "atr": None, "avg_atr": None}

        close_prices = [c.get("close", 0) for c in candles]
        avg_price = sum(close_prices[-20:]) / min(len(close_prices), 20) if len(close_prices) >= 2 else 1
        atr_pct = (atr / avg_price) * 100 if avg_price > 0 else 0

        if not hasattr(self, "_atr_cache"):
            self._atr_cache = {}
        cache_key = candles[-1].get("close", 0)
        cached_avg = self._atr_cache.get("avg_atr_pct")
        if cached_avg is None:
            self._atr_cache["avg_atr_pct"] = atr_pct
            cached_avg = atr_pct
        is_volatile = atr_pct > cached_avg * self.atr_mult

        last_close = close_prices[-1] if close_prices else 0
        return {
            "volatile": is_volatile,
            "atr": round(atr, 5),
            "atr_pct": round(atr_pct, 3),
            "avg_atr_pct": round(cached_avg, 3),
            "multiplier": self.atr_mult,
            "suggested_sl_points": round(atr * 1.5, 1) if atr else 20,
            "suggested_tp_points": round(atr * 3.0, 1) if atr else 40,
            "position_size_mult": round(min(1.0, cached_avg / atr_pct), 2) if atr_pct > 0 else 1.0,
        }

    def analyze(self, candles) -> str | None:
        if len(candles) < max(self.bb_period, self.rsi_period) + 1:
            return None
        close_prices = [c["close"] for c in candles]
        last_close = close_prices[-1]
        upper_bb, sma, lower_bb = self.calculate_bollinger_bands(close_prices)
        rsi = self.calculate_rsi(close_prices)
        vol_state = self.get_volatility_state(candles)

        if not upper_bb or not rsi:
            return None

        if vol_state["volatile"]:
            logger.info(
                f"Volatilidade elevada detectada (ATR%={vol_state['atr_pct']:.2f} "
                f"> media={vol_state['avg_atr_pct']:.2f}x{vol_state['multiplier']}). "
                f"Reduzindo tamanho da posicao para {vol_state['position_size_mult']*100:.0f}%"
            )

        if last_close < lower_bb and rsi < 15:
            return "call"
        if last_close > upper_bb and rsi > 85:
            return "put"
        return None
