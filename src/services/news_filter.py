"""
Filtro de Notícias Econômicas — RDE Platform
Usa o feed JSON público do ForexFactory para bloquear trades
próximos a eventos de alto impacto.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

try:
    import requests
except ImportError:
    requests = None

logger = logging.getLogger("rde")

FF_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
CACHE: dict = {"data": None, "fetched_at": None}
CACHE_TTL = timedelta(hours=1)

HIGH_IMPACT_TITLES = [
    "Non-Farm Employment Change",
    "CPI", "Consumer Price Index",
    "Interest Rate Decision",
    "Fed", "FOMC",
    "GDP",
    "Retail Sales",
    "Industrial Production",
    "Unemployment Rate",
    "ISM Manufacturing",
    "ISM Services",
    "NFP",
    "Core CPI",
    "PPI",
    "Producer Price Index",
    "Initial Jobless Claims",
    "Michigan Consumer Sentiment",
    "Existing Home Sales",
    "New Home Sales",
    "Consumer Confidence",
    "NFIB Business Optimism",
    "Durable Goods Orders",
    "Trade Balance",
    "Factory Orders",
    "Building Permits",
    "Housing Starts",
]


def _fetch_calendar() -> list[dict]:
    now = datetime.now(timezone.utc)
    if CACHE["data"] and CACHE["fetched_at"] and (now - CACHE["fetched_at"]) < CACHE_TTL:
        return CACHE["data"]
    if not requests:
        logger.warning("requests nao disponivel — news filter desativado")
        return []
    try:
        resp = requests.get(FF_URL, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        CACHE["data"] = data
        CACHE["fetched_at"] = now
        logger.info(f"Calendario economico atualizado: {len(data)} eventos")
        return data
    except Exception as e:
        logger.warning(f"Falha ao buscar calendario economico: {e}")
        return []


def _is_high_impact(event: dict) -> bool:
    title = (event.get("title") or "").lower()
    impact = (event.get("impact") or "").lower()
    if impact in ("high", "holy", "nonfarm"):
        return True
    for kw in HIGH_IMPACT_TITLES:
        if kw.lower() in title:
            return True
    return False


def get_upcoming_high_impact(minutes: int = 30) -> list[dict]:
    events = _fetch_calendar()
    now = datetime.now(timezone.utc)
    upcoming = []
    for ev in events:
        if not _is_high_impact(ev):
            continue
        try:
            ev_time_str = ev.get("date", "")
            ev_time = datetime.fromisoformat(ev_time_str)
        except (ValueError, TypeError):
            try:
                ev_time_str = ev.get("date", "")
                ev_time = datetime.strptime(ev_time_str, "%Y-%m-%dT%H:%M:%S%z")
            except (ValueError, TypeError):
                continue
        diff = (ev_time - now).total_seconds() / 60
        if 0 <= diff <= minutes:
            upcoming.append({
                "title": ev.get("title", "Unknown"),
                "time": ev_time.isoformat(),
                "impact": ev.get("impact", "high"),
                "currency": ev.get("country", ""),
                "minutes_away": round(diff, 1),
            })
    return upcoming


def is_blocked_by_news(minutes_before: int = 15, minutes_after: int = 15) -> Optional[dict]:
    events = _fetch_calendar()
    now = datetime.now(timezone.utc)
    for ev in events:
        if not _is_high_impact(ev):
            continue
        try:
            ev_time_str = ev.get("date", "")
            ev_time = datetime.fromisoformat(ev_time_str)
        except (ValueError, TypeError):
            continue
        diff = (ev_time - now).total_seconds() / 60
        if -minutes_after <= diff <= minutes_before:
            block_type = "before" if diff > 0 else "after"
            return {
                "blocked": True,
                "reason": f"Evento de alto impacto: {ev.get('title', 'Unknown')}",
                "event_title": ev.get("title", "Unknown"),
                "event_time": ev_time.isoformat(),
                "minutes_away": round(diff, 1),
                "block_type": block_type,
            }
    return None
