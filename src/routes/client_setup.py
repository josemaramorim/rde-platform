"""
Client setup: configura URL do servidor admin (ex: via Cloudflare Tunnel).
"""
import json, os, logging
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Client Setup"])

ADMIN_CONFIG_FILE = Path("admin_config.json")


def _load_admin_config() -> dict:
    if ADMIN_CONFIG_FILE.exists():
        try:
            return json.loads(ADMIN_CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_admin_config(data: dict):
    ADMIN_CONFIG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def get_saved_admin_url() -> Optional[str]:
    cfg = _load_admin_config()
    return cfg.get("admin_server_url") or None


class AdminServerConfigResponse(BaseModel):
    configured: bool
    admin_server_url: str


class AdminServerConfigRequest(BaseModel):
    admin_server_url: str


@router.get("/api/admin-server-config", response_model=AdminServerConfigResponse)
async def get_admin_server_config():
    from src.core.config import settings
    url = settings.ADMIN_SERVER_URL or get_saved_admin_url() or ""
    configured = bool(url) and "SEU_IP" not in url.upper()
    return AdminServerConfigResponse(configured=configured, admin_server_url=url)


@router.post("/api/admin-server-config", response_model=AdminServerConfigResponse)
async def save_admin_server_config(body: AdminServerConfigRequest):
    url = body.admin_server_url.strip()
    if url and not url.startswith("http"):
        raise HTTPException(status_code=400, detail="URL deve começar com http:// ou https://")
    _save_admin_config({"admin_server_url": url})
    configured = bool(url) and "SEU_IP" not in url.upper()
    return AdminServerConfigResponse(configured=configured, admin_server_url=url)
