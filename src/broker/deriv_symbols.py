"""
Mapeamento de simbolos Deriv — compartilhado entre copier, MT4 bridge e broker.
Ativos de volatilidade sintetica, crash/step, range break e forex.
"""
import re
import logging

logger = logging.getLogger("rde")

DERIV_SYMBOL_MAP = {
    # Mapeamento para ativos sinteticos (R_*) como proxy para forex.
    # Cada par tem um R_* unico para evitar colisoes.
    "EURUSD": "R_100", "GBPUSD": "R_75",  "USDJPY": "R_50",
    "AUDUSD": "R_25",  "USDCAD": "R_10",  "USDCHF": "R_75",
    "NZDUSD": "R_25",  "EURGBP": "R_50",  "EURJPY": "R_25",
    "GBPJPY": "R_10",  "XAUUSD": "1HZ250V", "BTCUSD": "cryBTCUSD",
    "ETHUSD": "cryETHUSD",

    # Volatility Indices
    "V10":    "1HZ10V",   "V10S":   "1HZ10V",
    "V25":    "1HZ25V",   "V25S":   "1HZ25V",
    "V50":    "1HZ50V",   "V50S":   "1HZ50V",
    "V75":    "1HZ75V",   "V75S":   "1HZ75V",
    "V100":   "1HZ100V",  "V100S":  "1HZ100V",
    "V250":   "1HZ250V",  "V250S":  "1HZ250V",

    "VOLATILITY_10":  "1HZ10V",
    "VOLATILITY_25":  "1HZ25V",
    "VOLATILITY_50":  "1HZ50V",
    "VOLATILITY_75":  "1HZ75V",
    "VOLATILITY_100": "1HZ100V",
    "VOLATILITY_250": "1HZ250V",

    # Crash / Boom
    "CRASH1000": "CRASH1000", "CRASH_1000": "CRASH1000",
    "CRASH500":  "CRASH500",  "CRASH_500":  "CRASH500",
    "CRASH300":  "CRASH300",  "CRASH_300":  "CRASH300",
    "CRASH100":  "CRASH100",  "CRASH_100":  "CRASH100",
    "BOOM1000":  "BOOM1000",  "BOOM_1000":  "BOOM1000",
    "BOOM500":   "BOOM500",   "BOOM_500":   "BOOM500",
    "BOOM300":   "BOOM300",   "BOOM_300":   "BOOM300",
    "BOOM100":   "BOOM100",   "BOOM_100":   "BOOM100",

    # Step Index
    "STEP10":  "STPUSD", "STEP_10": "STPUSD", "STEP_INDEX": "STPUSD",
    "STEP25":  "STPUSD", "STEP_25": "STPUSD",
    "STEP50":  "STPUSD", "STEP_50": "STPUSD",

    # Range Break
    "RANGE_BREAK10":  "RBBREAKU", "RBB10": "RBBREAKU",
    "RANGE_BREAK50":  "RBBREAKU", "RBB50": "RBBREAKU",
}


def resolve_deriv_symbol(raw_symbol: str) -> str:
    """
    Resolve um simbolo cru (do sinal Telegram/MT4) para o formato Deriv.
    Tenta match exato, depois strip OTC e tenta de novo.
    Retorna o simbolo Deriv ou 'R_100' como default.
    """
    sym = raw_symbol.upper().strip()
    sym = re.sub(r'[^A-Z0-9_\-]', '', sym)

    # Match exato
    if sym in DERIV_SYMBOL_MAP:
        return DERIV_SYMBOL_MAP[sym]

    # Strip OTC e tenta de novo
    base = re.sub(r'[-_]OTC[A-Z]?$', '', sym)
    if base in DERIV_SYMBOL_MAP:
        return DERIV_SYMBOL_MAP[base]

    # Ja e um simbolo Deriv direto?
    deriv_direct = {
        "R_10": True, "R_25": True, "R_50": True, "R_75": True, "R_100": True,
        "1HZ10V": True, "1HZ25V": True, "1HZ50V": True, "1HZ75V": True, "1HZ100V": True, "1HZ250V": True,
        "CRASH1000": True, "CRASH500": True, "CRASH300": True, "CRASH100": True,
        "BOOM1000": True, "BOOM500": True, "BOOM300": True, "BOOM100": True,
        "STPUSD": True, "RBBREAKU": True, "cryBTCUSD": True, "cryETHUSD": True,
    }
    if sym in deriv_direct:
        return sym

    # Fallback inteligente: tenta mapear por prefixo
    for prefix, deriv_sym in [
        ("EURUSD", "R_100"), ("GBPUSD", "R_75"), ("USDJPY", "R_50"),
        ("AUDUSD", "R_25"), ("USDCAD", "R_10"), ("USDCHF", "R_75"),
        ("NZDUSD", "R_25"), ("EURGBP", "R_50"), ("EURJPY", "R_25"),
        ("GBPJPY", "R_10"), ("XAUUSD", "1HZ250V"), ("XAGUSD", "1HZ250V"),
        ("BTCUSD", "cryBTCUSD"), ("ETHUSD", "cryETHUSD"),
    ]:
        if sym.startswith(prefix):
            logger.warning(f"[DERIV] Ativo '{raw_symbol}' mapeado por prefixo -> {deriv_sym}")
            return deriv_sym

    logger.warning(f"[DERIV] Ativo '{raw_symbol}' sem mapeamento. Usando R_100 como fallback.")
    return "R_100"


def get_deriv_symbol_map() -> dict:
    """Retorna copia do mapa completo."""
    return dict(DERIV_SYMBOL_MAP)
