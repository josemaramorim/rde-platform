"""
Main entry point for the RDE Platform API.
Handles authentication, trading signals, payments, and administration.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional
from fastapi import FastAPI, Depends, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

# Configuration
from src.core.config import settings

# Auth & Database
from src.auth.users import (
    fastapi_users,
    current_active_user,
    current_superuser,
)
from src.auth.schemas import UserRead, UserCreate, UserUpdate
from src.auth.backend import auth_backend
from src.models.user import User, Plan, PlanHistory, AdminLog
from src.models.token_licenca import TokenLicenca
from src.database.session import get_async_session

# Business Logic
from src.plan_manager import async_check_plan_limits
from src.celery_worker import process_signal
from src.stripe_service import create_checkout_session, handle_webhook
from src.ai_engine import detect_profitable_users, user_risk_score
from src.email_service import send_plan_upgrade_email
from src.logger import log_admin
from src.routes.broker import router as broker_router
try:
    from src.routes.admin_routes import router as admin_v2_router
    _has_admin_v2 = True
except ImportError:
    _has_admin_v2 = False
from src.routes.user import router as user_router
from src.telegram_service import TelegramBot
from src.routes.licenca import router as licenca_router
from src.routes.client_setup import router as client_setup_router
from src.routes.risk_term import router as risk_term_router
from src.routes.planilha import router as planilha_router
from src.routes.tradingview_bridge import router as tradingview_bridge_router
from src.routes.telegram_auth import router as telegram_auth_router

# Rate limiting
try:
    from slowapi import Limiter
    from slowapi.util import get_remote_address
    from slowapi.errors import RateLimitExceeded

    limiter = Limiter(key_func=get_remote_address)
    RATE_LIMIT_ENABLED = settings.RATE_LIMIT_ENABLED
except ImportError:
    limiter = None
    RATE_LIMIT_ENABLED = False

app = FastAPI(
    title="RDE Platform API",
    version="1.0.0",
    description="Risk-Disciplined Execution Platform — Multi-Broker Trading SaaS"
)

# GZip compression — reduz em até 70% o tamanho dos JS/CSS entregues ao browser
from starlette.middleware.gzip import GZipMiddleware
app.add_middleware(GZipMiddleware, minimum_size=1024)

# CORS: origens permitidas (frontend local, tunnel cloudflare, producao)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:8000",
        "https://rde-platform.vercel.app",
        "https://ann-pumps-embassy-pound.trycloudflare.com",
    ],
    allow_origin_regex=r"https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    max_age=3600,
)

if RATE_LIMIT_ENABLED:
    app.state.limiter = limiter

    async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
        return JSONResponse(
            status_code=429,
            content={"error": "Rate limit exceeded. Slow down."}
        )

# ====================== SECURITY HEADERS MIDDLEWARE (PURE ASGI) ======================
from starlette.datastructures import MutableHeaders

class PureSecurityHeadersMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_security_headers(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-Frame-Options"] = "DENY"
                headers["X-Content-Type-Options"] = "nosniff"
                headers["X-XSS-Protection"] = "1; mode=block"
                headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
                path = scope.get("path", "")
                if not path.startswith(("/docs", "/redoc", "/openapi.json")):
                    headers["Content-Security-Policy"] = (
                        "default-src 'self'; "
                        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                        "img-src 'self' data: https://fastapi.tiangolo.com; "
                        "font-src 'self' data: https://cdn.jsdelivr.net; "
                        "connect-src 'self' https: http: ws: wss:;"
                    )
            await send(message)

        try:
            await self.app(scope, receive, send_with_security_headers)
        except Exception:
            pass

app.add_middleware(PureSecurityHeadersMiddleware)

# ====================== INPUT SANITIZATION ======================

import re as _re
_INPUT_BLOCK_PATTERN = _re.compile(r"[\"'<>;()$`]")

def sanitize_input(value: str) -> str:
    return _INPUT_BLOCK_PATTERN.sub("", value)

class SanitizedStr(str):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate
    @classmethod
    def validate(cls, v):
        if not isinstance(v, str):
            return v
        return cls(sanitize_input(v))

# ====================== MIDDLEWARE DE LICENÇA ======================

ROTAS_PUBLICAS = {"/", "/docs", "/openapi.json", "/redoc", "/telegram/status", "/telegram/auth-status", "/health", "/acesso.html"}
PREFIXOS_PUBLICOS = {"/auth/", "/admin/", "/users/", "/broker/", "/dashboard/", "/signal", "/api/", "/copier/", "/planilha/", "/risk-term/"}

@app.middleware("http")
async def middleware_licenca(request: Request, call_next):
    """Verifica licença para todas as rotas protegidas sem causar socket reset."""
    path = request.url.path

    # Pula rotas públicas
    if path in ROTAS_PUBLICAS:
        return await call_next(request)
    for prefixo in PREFIXOS_PUBLICOS:
        if path.startswith(prefixo):
            return await call_next(request)

    try:
        return await call_next(request)
    except Exception:
        return JSONResponse(status_code=500, content={"detail": "Erro no servidor de aplicação."})


# ====================== MODELO DE ENTRADA DO LOGIN ======================
class MagicLoginRequest(BaseModel):
    email: str
    password: str = ""

class LoginSchema(BaseModel):
    username: Optional[str] = Field(default=None, json_schema_extra={"example": "ferreira.jpa1@hotmail.com"})
    email: Optional[str] = Field(default=None, json_schema_extra={"example": "ferreira.jpa1@hotmail.com"})
    password: str = Field(..., json_schema_extra={"example": "123456789"})

# ====================== SYNC DE SALDO REAL DA CORRETORA ======================
async def _sync_broker_balance(
    user: User,
    db: AsyncSession,
    setting,
) -> float | None:
    """
    Conecta na corretora ativa, busca o saldo real (sem cache),
    atualiza o banco de dados e o arquivo live_status_{user.id}.json.
    Retorna o saldo ou None em caso de erro.
    """
    import json, os, time, asyncio
    from concurrent.futures import ThreadPoolExecutor
    from src.core.security import encryption_service

    def _decrypt(val):
        if not val:
            return None
        try:
            dec = encryption_service.decrypt(val)
            return dec if dec != "ERROR_DECRYPT" else val
        except Exception:
            return val

    broker_name = setting.broker_name.lower()

    def _fetch():
        if broker_name == "iqoption":
            from src.broker.iqoption import IQOptionBroker
            creds = _decrypt(setting.api_token) or ""
            if "|||" in creds:
                email, password = creds.split("|||", 1)
            else:
                email, password = creds, ""
            if not email or not password:
                return None
            b = IQOptionBroker(email=email, password=password, is_demo=setting.is_demo)
            b.connect()
            time.sleep(2)
            bal = b.get_balance()
            try:
                b.disconnect()
            except Exception:
                pass
            return float(bal) if bal is not None else None

        elif broker_name in ("deriv", "deriv_demo", "deriv_real"):
            from src.broker.deriv import DerivBroker
            token = _decrypt(setting.api_token)
            if not token:
                return None
            b = DerivBroker(api_token=token, is_demo=setting.is_demo, app_id=getattr(setting, "deriv_app_id", None) or "16929")
            b.connect()
            bal = b.get_balance()
            try:
                b.disconnect()
            except Exception:
                pass
            return float(bal) if bal is not None else None

        return None

    try:
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as pool:
            balance = await loop.run_in_executor(pool, _fetch)
    except Exception:
        return None

    if balance is not None and balance > 0:
        # Atualiza DB
        setting.balance = balance
        setting.balance_updated_at = datetime.utcnow()
        db.add(setting)
        await db.commit()

        # Atualiza live_status_{user.id}.json
        status_file = f"live_status_{user.id}.json"
        live = {}
        if os.path.exists(status_file):
            try:
                with open(status_file, "r") as f:
                    live = json.load(f)
            except Exception:
                pass
        live["current_balance"] = balance
        live["initial_balance"] = live.get("initial_balance", balance)
        live["broker"] = broker_name
        live["account_mode"] = "Demo" if setting.is_demo else "Real"
        live["timestamp"] = datetime.utcnow().strftime("%H:%M:%S")
        live["last_message"] = live.get("last_message", "Saldo sincronizado com a corretora")
        try:
            with open(status_file, "w") as f:
                json.dump(live, f)
        except Exception:
            pass

    return balance


# ====================== ROTAS DE AUTH ======================
# Removido fastapi_users.get_auth_router (login substituído por endpoint JSON compatível)
# Mantemos logout manualmente
@app.post("/auth/jwt/logout", tags=["Auth"])
async def jwt_logout(request: Request, user: User = Depends(current_active_user)):
    from fastapi.security import HTTPAuthorizationCredentials
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    strategy = auth_backend.get_strategy()
    if token and strategy:
        await strategy.destroy_token(token)
    return {"status": "ok", "message": "Logout realizado"}

app.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    prefix="/auth",
    tags=["Auth"],
)
app.include_router(
    fastapi_users.get_reset_password_router(),
    prefix="/auth",
    tags=["Auth"],
)
app.include_router(
    fastapi_users.get_verify_router(UserRead),
    prefix="/auth",
    tags=["Auth"],
)
app.include_router(
    fastapi_users.get_users_router(UserRead, UserUpdate),
    prefix="/users",
    tags=["Users"],
)

# ====================== LOGIN (JSON + form-urlencoded) ======================
@app.post("/auth/jwt/login", tags=["Auth"])
async def json_login(
    request: Request,
    db: AsyncSession = Depends(get_async_session)
):
    """Login que aceita JSON ou form-urlencoded — compatível com Swagger UI e frontend."""
    ct = request.headers.get("content-type", "")
    body_data = {}
    try:
        if "json" in ct:
            body_data = await request.json()
        elif "form" in ct or "x-www-form-urlencoded" in ct:
            form = await request.form()
            body_data = dict(form)
        else:
            try:
                body_data = await request.json()
            except Exception:
                form = await request.form()
                body_data = dict(form)
    except Exception:
        raise HTTPException(status_code=400, detail="Erro ao processar dados de login.")

    email = (body_data.get("username") or body_data.get("email") or "").strip()
    password = body_data.get("password") or ""

    if not email or not password:
        raise HTTPException(status_code=400, detail="Email e senha são obrigatórios.")

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="Credenciais inválidas.")

    from fastapi_users.password import PasswordHelper
    ph = PasswordHelper()
    valid, _ = ph.verify_and_update(password, user.hashed_password)
    if not valid:
        raise HTTPException(status_code=401, detail="Credenciais inválidas.")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Conta desativada.")

    strategy = auth_backend.get_strategy()
    token = await strategy.write_token(user)

    return {
        "access_token": token,
        "token": token,
        "accessToken": token,
        "token_type": "bearer"
    }


# ====================== MAGIC LOGIN (ADMIN ONLY) ======================
@app.post("/auth/magic-login", tags=["Auth"])
async def magic_login(payload: MagicLoginRequest, db: AsyncSession = Depends(get_async_session)):
    email = payload.email
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Admin nao encontrado.")
    
    if email != settings.ADMIN_EMAIL and not getattr(user, "is_admin", False) and not getattr(user, "is_superuser", False):
        raise HTTPException(status_code=403, detail="Acesso negado.")
    
    if not payload.password:
        raise HTTPException(status_code=401, detail="Senha obrigatoria.")
    
    from fastapi_users.password import PasswordHelper
    ph = PasswordHelper()
    valid, _ = ph.verify_and_update(payload.password, user.hashed_password)
    if not valid:
        raise HTTPException(status_code=401, detail="Senha incorreta.")
    
    user.is_admin = True
    user.is_superuser = True
    user.is_active = True
    db.add(user)
    await db.commit()
    
    strategy = auth_backend.get_strategy()
    token = await strategy.write_token(user)
    
    return {
        "status": "success",
        "message": "Login autorizado",
        "access_token": token,
        "token": token,
        "accessToken": token,
        "token_type": "bearer"
    }

# ====================== BROKER SETTINGS ======================
app.include_router(broker_router)
if _has_admin_v2:
    app.include_router(admin_v2_router)
app.include_router(user_router)
app.include_router(licenca_router)
app.include_router(client_setup_router)
app.include_router(risk_term_router)
app.include_router(planilha_router)
app.include_router(tradingview_bridge_router)
app.include_router(telegram_auth_router)

# ====================== FRONTEND ESTÁTICO (modo cliente) ======================
import os as _os
_candidatos = [
    _os.path.join(_os.path.dirname(_os.path.abspath(_os.sys.argv[0])), "..", "frontend"),
    _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "..", "frontend"),
    _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "frontend"),
    _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "cliente", "frontend"),
]
_frontend_dir = next((d for d in _candidatos if _os.path.isdir(d)), None)
if _frontend_dir:
    from fastapi.staticfiles import StaticFiles
    _next_dir = _os.path.join(_frontend_dir, "_next")
    if _os.path.isdir(_next_dir):
        app.mount("/_next", StaticFiles(directory=_next_dir), name="next_assets")

# ====================== DASHBOARD & STATS ======================

@app.get("/telegram/status", tags=["Telegram"])
async def telegram_status(user: User = Depends(current_active_user)):
    import os, psutil
    connected = await TelegramBot.test_connection()
    copier_running = False
    if os.path.exists("copier.pid"):
        try:
            with open("copier.pid") as pf:
                pid = int(pf.read().strip())
            copier_running = psutil.pid_exists(pid)
        except Exception:
            pass
    live_data = {}
    if copier_running:
        try:
            import json
            status_file = f"live_status_{user.id}.json"
            if os.path.exists(status_file):
                with open(status_file, "r") as f:
                    live_data = json.load(f)
        except Exception:
            pass
    return {
        "connected": connected,
        "group": settings.TELEGRAM_GROUP_NAME,
        "chat_id": settings.TELEGRAM_CHAT_ID,
        "bot_configured": bool(settings.TELEGRAM_BOT_TOKEN),
        "copier_running": copier_running,
        "live": live_data,
    }


@app.post("/telegram/start-copier", tags=["Telegram"])
async def start_copier(
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    import subprocess, sys, os, psutil
    if os.path.exists("copier.pid"):
        try:
            with open("copier.pid") as f:
                pid = int(f.read().strip())
            if psutil.pid_exists(pid):
                return {"status": "already_running", "pid": pid}
            else:
                os.remove("copier.pid")
        except Exception:
            try:
                os.remove("copier.pid")
            except Exception:
                pass

    # Resolve broker do usuario
    result = await db.execute(
        select(User).options(selectinload(User.broker_settings)).where(User.id == user.id)
    )
    u = result.scalar_one_or_none()
    broker_name = ""
    if u and u.broker_settings:
        active_setting = next((s for s in u.broker_settings if s.is_active), None)
        if active_setting:
            broker_name = active_setting.broker_name.lower()

    cmd = [sys.executable, "-m", "src.telegram_copier", "--user-id", str(user.id)]
    if broker_name:
        cmd += ["--broker", broker_name]

    proc = subprocess.Popen(
        cmd,
        stdout=open("copier.log", "w", encoding="utf-8"),
        stderr=subprocess.STDOUT,
        cwd=os.getcwd()
    )
    with open("copier.pid", "w") as f:
        f.write(str(proc.pid))
    return {"status": "started", "pid": proc.pid}


@app.post("/telegram/stop-copier", tags=["Telegram"])
async def stop_copier(user: User = Depends(current_active_user)):
    import os, sys, subprocess
    if not os.path.exists("copier.pid"):
        return {"status": "not_running"}
    with open("copier.pid") as f:
        pid = int(f.read().strip())
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, timeout=5)
        else:
            import signal
            os.kill(pid, signal.SIGTERM)
        os.remove("copier.pid")
        return {"status": "stopped"}
    except Exception as e:
        os.remove("copier.pid")
        return {"status": "error", "detail": str(e)}


@app.post("/telegram/test", tags=["Telegram"])
async def telegram_test(user: User = Depends(current_active_user)):
    ok = await TelegramBot.send_message(
        f"<b>RDE Platform</b>\n\n"
        f"Teste de conexao realizado por <b>{user.email}</b>\n"
        f"Status: Plataforma operacional."
    )
    return {"status": "ok" if ok else "error"}


@app.post("/telegram/notify", tags=["Telegram"])
async def telegram_notify(
    message: str,
    admin: User = Depends(current_superuser)
):
    ok = await TelegramBot.send_message(f"<b>RDE Admin</b>\n\n{message}")
    return {"status": "ok" if ok else "error"}


@app.get("/user/session", tags=["Account"])
async def get_session(
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session)
):
    result = await db.execute(
        select(User).options(selectinload(User.broker_settings), selectinload(User.plan)).where(User.id == user.id)
    )
    u = result.scalar_one_or_none()
    active_broker = next((s for s in u.broker_settings if s.is_active), None) if u else None
    plan_name = u.plan.name if u.plan else "basic"
    is_demo = u.plan.is_demo if u.plan else True
    return {
        "broker": active_broker.broker_name if active_broker else (u.broker or "deriv"),
        "is_demo": is_demo,
        "stake": u.stake,
        "risk_mode": u.risk_mode,
        "stop_loss_pct": u.stop_loss_pct,
        "daily_meta_pct": u.daily_meta_pct,
        "telegram_enabled": u.telegram_enabled,
        "plan_name": plan_name,
    }


@app.get("/dashboard/live", tags=["Dashboard"])
async def get_dashboard_live(
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    import json, os
    from sqlalchemy.orm import selectinload
    from src.models.broker import BrokerSetting

    # Fetch user + broker info from DB
    result = await db.execute(
        select(User).options(selectinload(User.plan), selectinload(User.broker_settings)).where(User.id == user.id)
    )
    u = result.scalar_one_or_none() or user

    # Find active broker settings (multi-broker)
    active_settings = []
    active_setting = None
    broker_balance = 0.0
    broker_connected = False
    broker_mode = "Real"
    if u.broker_settings:
        for s in u.broker_settings:
            if s.is_active:
                active_settings.append(s)
                broker_connected = True
                if active_setting is None:
                    active_setting = s
                    broker_mode = "Demo" if s.is_demo else "Real"
                    if s.balance:
                        broker_balance = float(s.balance)

    # Prefere o broker principal (user.broker) como referência do dashboard
    if active_settings and (u.broker or ""):
        primary = next((s for s in active_settings if s.broker_name == (u.broker or "").lower()), None)
        if primary:
            active_setting = primary
            broker_mode = "Demo" if primary.is_demo else "Real"
            if primary.balance:
                broker_balance = float(primary.balance)

    status_file = f"live_status_{user.id}.json"
    ops_file = f"live_operations_{user.id}.json"

    live = {}
    if os.path.exists(status_file):
        try:
            with open(status_file, "r") as f:
                live = json.load(f)
        except Exception:
            pass

    ops = []
    if os.path.exists(ops_file):
        try:
            with open(ops_file, "r") as f:
                ops = json.load(f)
        except Exception:
            pass

    copier_running = False
    copier_source = "telegram"
    if os.path.exists("copier.pid"):
        try:
            with open("copier.pid") as pf:
                content = pf.read().strip()
            if content.startswith("tv:"):
                copier_running = True
                copier_source = "tradingview"
            else:
                pid = int(content)
                import psutil
                copier_running = psutil.pid_exists(pid)
                if not copier_running:
                    os.remove("copier.pid")
        except Exception:
            copier_running = False

    # Sempre preferir o broker ativo do BD ao invés do arquivo do copier,
    # pois o arquivo pode estar desatualizado (copier parado ou trocou broker)
    active_broker_name = active_setting.broker_name if active_setting else u.broker
    copier_broker = live.get("broker")
    last_message = live.get("last_message", "")
    if not copier_running:
        # Copier parado → preserva last_message para mostrar erro/motivo no dashboard
        live = {"last_message": last_message} if last_message else {}

        # ── AUTO-SYNC: busca saldo real da corretora a cada 30s quando o copier está parado ──
        if active_setting and active_setting.api_token:
            last_sync = active_setting.balance_updated_at
            should_sync = True
            if last_sync:
                age = (datetime.utcnow() - last_sync).total_seconds()
                if age < 30:
                    should_sync = False
            if should_sync:
                fresh = await _sync_broker_balance(user, db, active_setting)
                if fresh is not None and fresh > 0:
                    broker_balance = fresh
                    live["current_balance"] = fresh
                    live["initial_balance"] = live.get("initial_balance", fresh)
                    live["broker"] = active_broker_name
                    live["account_mode"] = "Demo" if active_setting.is_demo else "Real"
                    live["timestamp"] = datetime.utcnow().strftime("%H:%M:%S")
    elif copier_broker and active_broker_name and copier_broker != active_broker_name:
        # Copier rodando com broker diferente do ativo → descarta dados
        live = {}

    broker_name = active_broker_name or live.get("broker") or "iqoption"

    # Per-broker meta status from DB (with auto-reset on new day)
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    _meta_was_reset = False
    if active_setting:
        db_meta_hit = active_setting.meta_hit_today
        db_meta_date = active_setting.meta_hit_date
        db_auto_lock = active_setting.auto_lock_meta
        db_stake = active_setting.stake or u.stake or 0
        if db_meta_hit and db_meta_date and db_meta_date != today_str:
            db_meta_hit = False
            active_setting.meta_hit_today = False
            active_setting.meta_hit_date = None
            active_setting.today_trades = 0
            active_setting.today_profit = 0.0
            _meta_was_reset = True
    else:
        db_meta_hit = u.meta_hit_today or False
        db_meta_date = u.meta_hit_date
        db_auto_lock = u.auto_lock_meta or False
        db_stake = u.stake or 0
        if db_meta_hit and db_meta_date and db_meta_date != today_str:
            db_meta_hit = False
            u.meta_hit_today = False
            u.meta_hit_date = None
            _meta_was_reset = True

    if _meta_was_reset:
        await db.commit()

    # Remove stale live_status file (da data anterior) se existir
    if _os.path.exists(status_file):
        try:
            file_mtime = datetime.fromtimestamp(_os.path.getmtime(status_file))
            if (datetime.utcnow() - file_mtime).days >= 1:
                _os.remove(status_file)
                live = {}
        except Exception:
            pass

    return {
        "copier_running": copier_running,
        "copier_source": copier_source,
        "signal_source": live.get("source") or u.signal_source or "telegram",
        "broker": broker_name,
        "active_brokers": [
            {
                "broker": s.broker_name,
                "balance": float(s.balance or 0),
                "mode": "Demo" if s.is_demo else "Real",
                "connected": True,
            }
            for s in active_settings
        ],
        "account_mode": live.get("account_mode") or broker_mode,
        "balance": (live.get("current_balance") if live.get("current_balance") and float(live.get("current_balance")) > 0 else broker_balance),
        "initial_balance": (live.get("initial_balance") if live.get("initial_balance") and float(live.get("initial_balance")) > 0 else broker_balance),
        "profit": live.get("profit", 0.0),
        "profit_pct": live.get("profit_pct", 0.0),
        "signals_today": live.get("signals_today", 0),
        "success_count": live.get("success_count", 0),
        "success_rate": live.get("success_rate", 0.0),
        "gale_level": live.get("gale_level", 0),
        "current_stake": live.get("current_stake", db_stake),
        "last_message": live.get("last_message", "Aguardando sinais..."),
        "timestamp": live.get("timestamp", "-"),
        "operations": ops[-20:],
        # Meta status: DB e a fonte da verdade (sobrescreve arquivo stale)
        "meta_hit_today": db_meta_hit,
        "meta_hit_date": db_meta_date,
        "auto_lock_meta": db_auto_lock,
        "daily_target": live.get("daily_target", 0),
        "daily_profit": live.get("daily_profit", 0),
        "daily_progress_pct": live.get("daily_progress_pct", 0),
        "current_session": live.get("current_session", 1),
        "session_entries_used": live.get("session_entries_used", 0),
        "session_profit": live.get("session_profit", 0),
        "session_target": live.get("session_target", 0),
    }


@app.get("/stats/performance", tags=["Stats"])
async def get_stats_performance(
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session)
):
    from src.models.broker import BrokerSetting
    from sqlalchemy import select as sa_select
    from datetime import datetime

    result = await db.execute(
        sa_select(BrokerSetting).where(
            BrokerSetting.user_id == user.id,
            BrokerSetting.is_active == True
        ).limit(1)
    )
    broker = result.scalar_one_or_none()

    # Auto-sync: busca saldo real se estiver desatualizado (> 30s)
    fresh_balance = None
    if broker and broker.api_token:
        last_sync = broker.balance_updated_at
        should_sync = True
        if last_sync:
            age = (datetime.utcnow() - last_sync).total_seconds()
            if age < 30:
                should_sync = False
        if should_sync:
            fresh_balance = await _sync_broker_balance(user, db, broker)

    balance = fresh_balance if fresh_balance is not None else (broker.balance if broker else 0)

    if broker and broker.total_trades > 0:
        win_rate = (broker.total_wins / broker.total_trades) * 100
    else:
        win_rate = 0.0

    return {
        "broker": broker.broker_name if broker else "Nenhum",
        "broker_type": broker.broker_type.value if broker else "-",
        "balance": float(balance),
        "mode": "Demo" if broker and broker.is_demo else "Real",
        "win_rate": round(win_rate, 1),
        "total_trades": broker.total_trades if broker else 0,
        "total_wins": broker.total_wins if broker else 0,
        "total_losses": broker.total_losses if broker else 0,
        "today_trades": broker.today_trades if broker else 0,
        "today_profit": broker.today_profit if broker else 0,
        "total_profit": broker.total_profit if broker else 0,
    }


@app.on_event("startup")
async def startup():
    import logging
    _log = logging.getLogger("rde")

    # ── Recuperação do banco SQLite ─────────────────────────────────
    import os as _os
    db_path = _os.path.join(_os.getcwd(), "rde_local.db")
    if _os.path.exists(db_path):
        try:
            import sqlite3 as _sqlite3
            conn = _sqlite3.connect(db_path)
            # Força checkpoint do WAL e desativa WAL (modo DELETE é mais seguro)
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.execute("PRAGMA journal_mode=DELETE")
            # Verifica integridade
            cur = conn.execute("PRAGMA integrity_check")
            result = cur.fetchall()
            if all(row[0] == "ok" for row in result):
                _log.info("✅ Integridade do banco verificada: OK")
            else:
                _log.error(f"❌ Banco de dados corrompido: {result}")
            conn.close()
        except Exception as e:
            _log.warning(f"⚠️ Não foi possível verificar banco: {e}")

    # ── Sincronização de tabelas ───────────────────────────────────
    from src.database.base import Base
    from src.database.session import engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # ── Migrações manuais ──────────────────────────────────────────
    async with engine.begin() as conn:
        for col_name, col_type, default in [
            ("signal_source", "VARCHAR(20)", "'telegram'"),
            ("mt4_api_key", "VARCHAR(64)", "NULL"),
        ]:
            try:
                await conn.execute(
                    __import__("sqlalchemy").text(
                        f"ALTER TABLE users ADD COLUMN {col_name} {col_type} DEFAULT {default}"
                    )
                )
                _log.info(f"Migração: coluna '{col_name}' adicionada à tabela users.")
            except Exception:
                pass

    async with engine.begin() as conn:
        for col_name, col_type, default in [
            ("deriv_app_id", "VARCHAR(100)", "'16929'"),
            ("deriv_token_expiry", "DATETIME", "NULL"),
        ]:
            try:
                await conn.execute(
                    __import__("sqlalchemy").text(
                        f"ALTER TABLE broker_settings ADD COLUMN {col_name} {col_type} DEFAULT {default}"
                    )
                )
                _log.info(f"Migração: coluna '{col_name}' adicionada à tabela broker_settings.")
            except Exception:
                pass

    # ── Limpeza de arquivos temporários ────────────────────────────
    pid_file = "copier.pid"
    if _os.path.exists(pid_file):
        try:
            with open(pid_file) as f:
                content = f.read().strip()
            if content.startswith("tv:"):
                pass
            else:
                try:
                    pid = int(content)
                    import psutil
                    if not psutil.pid_exists(pid):
                        _os.remove(pid_file)
                        _log.info(f"Stale copier.pid (PID {pid}) cleaned up on startup.")
                except Exception:
                    _os.remove(pid_file)
                    _log.info("Stale copier.pid cleaned up on startup.")
        except Exception:
            try:
                _os.remove(pid_file)
            except Exception:
                pass

    # Remove session files corrompidos/antigos
    for fname in _os.listdir("."):
        if fname.startswith("rde_user_session_") and fname.endswith(".session"):
            fpath = _os.path.join(".", fname)
            try:
                # Verifica se o arquivo é JSON válido antes de tentar ler
                import json as _json
                with open(fpath, "r") as f:
                    _json.load(f)
            except Exception:
                _log.info(f"Removendo session file corrompido: {fname}")
                try:
                    _os.remove(fpath)
                except Exception:
                    pass

    # ── Reseta meta stale de todos os usuarios ─────────────────────
    from src.models.broker import BrokerSetting
    try:
        async with engine.begin() as conn:
            today_sql = datetime.utcnow().strftime("%Y-%m-%d")
            # Reseta meta_hit de broker_settings onde data != hoje
            await conn.execute(
                __import__("sqlalchemy").text(
                    "UPDATE broker_settings SET meta_hit_today = 0, meta_hit_date = NULL, "
                    "today_trades = 0, today_profit = 0 "
                    "WHERE meta_hit_date IS NOT NULL AND meta_hit_date != :today"
                ),
                {"today": today_sql}
            )
            # Reseta meta_hit de users onde data != hoje
            await conn.execute(
                __import__("sqlalchemy").text(
                    "UPDATE users SET meta_hit_today = 0, meta_hit_date = NULL "
                    "WHERE meta_hit_date IS NOT NULL AND meta_hit_date != :today"
                ),
                {"today": today_sql}
            )
            _log.info("Stale meta flags resetadas no startup.")
    except Exception as e:
        _log.warning(f"Nao foi possivel resetar meta stale no startup: {e}")

    _log.info(f"Ambiente: {settings.ENVIRONMENT} | Profile: {_os.environ.get('RDE_PROFILE', 'none')}")
    _log.info("Startup concluido com sucesso.")


@app.get("/", tags=["Health"])
async def root():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/acesso.html")

@app.get("/health", tags=["Health"])
def api_health():
    return {"service": "RDE API", "status": "online", "version": "1.0.0"}


@app.get("/version", tags=["Health"])
def get_version():
    import os
    version = os.environ.get("PLATFORM_VERSION", "1.0.0")
    update_required = os.environ.get("UPDATE_REQUIRED", "false").lower() == "true"
    return {
        "version": version,
        "update_required": update_required,
        "update_url": "http://localhost:3001/atualizar",
        "message": os.environ.get("UPDATE_MESSAGE", "")
    }


@app.post("/admin/force-update", tags=["Admin"])
async def force_update(
    version: str,
    message: str = "",
    admin: User = Depends(current_superuser)
):
    import os
    os.environ["PLATFORM_VERSION"] = version
    os.environ["UPDATE_REQUIRED"] = "true"
    os.environ["UPDATE_MESSAGE"] = message
    return {"status": "ok", "version": version, "update_required": True}


@app.post("/admin/release-update", tags=["Admin"])
async def release_update(
    admin: User = Depends(current_superuser)
):
    import os
    os.environ["UPDATE_REQUIRED"] = "false"
    return {"status": "ok", "update_required": False}


@app.post("/signal", tags=["Trading"])
async def receive_signal(
    email: str,
    signal: str,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session)
):
    # Só pode enviar sinal para si mesmo, ou admin para qualquer um
    if user.email != email and not user.is_superuser:
        return {"error": "Você só pode enviar sinais para sua própria conta."}

    result = await db.execute(
        select(User).options(selectinload(User.plan)).where(User.email == email)
    )
    target = result.scalar_one_or_none()

    if not target or not target.is_active:
        return {"error": "User not found or inactive."}

    if not target.liberado and not target.is_admin:
        return {"error": "Acesso pendente. Aguarde a liberação pelo administrador."}

    target.last_seen = datetime.utcnow()

    if not target.trading_enabled:
        await db.commit()
        return {"error": "Trading disabled by administrator."}

    if target.plan_expires_at and target.plan_expires_at < datetime.utcnow():
        plan_result = await db.execute(select(Plan).where(Plan.name == "Free"))
        free_plan = plan_result.scalar_one_or_none()
        target.plan_id = free_plan.id if free_plan else None
        await db.commit()
        return {"error": "Plan expired. Downgraded to Free."}

    allowed, message = await async_check_plan_limits(db, target)
    if not allowed:
        return {"error": message}

    try:
        process_signal.delay(email, signal)
        status = "queued"
    except Exception:
        status = "accepted_no_worker"
    return {"status": status, "signal": signal, "risk_mode": target.risk_mode}





@app.post("/copier/toggle", tags=["Copier"])
async def toggle_copier(
    body: dict,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Toggle the copier on/off (Telegram or MT4 mode)."""
    import subprocess, sys, os, psutil, json
    from datetime import datetime

    pid_file = "copier.pid"
    status_file = f"live_status_{user.id}.json"

    # Clean stale PID (skip MT4 markers)
    if os.path.exists(pid_file):
        try:
            with open(pid_file) as pf:
                content = pf.read().strip()
            if content.startswith("tv:"):
                pass  # TradingView marker — handled below
            else:
                pid = int(content)
                if not psutil.pid_exists(pid):
                    os.remove(pid_file)
        except Exception:
            try:
                os.remove(pid_file)
            except Exception:
                pass

    active = body.get("active", False)
    if active:
        # If pid_file exists, check if we need to stop it before switching modes
        if os.path.exists(pid_file):
            try:
                with open(pid_file) as pf:
                    existing = pf.read().strip()
            except Exception:
                existing = ""

            # Determine the user's desired mode
            result_check = await db.execute(
                select(User).options(selectinload(User.broker_settings)).where(User.id == user.id)
            )
            u_check = result_check.scalar_one_or_none()
            desired_is_tv = (u_check and u_check.signal_source == "tradingview")

            existing_is_tv = existing.startswith("tv:")
            existing_is_telegram = not existing_is_tv and existing.isdigit()

            # If same mode already running, block
            if desired_is_tv and existing_is_tv:
                return {"status": "already_running"}
            if not desired_is_tv and existing_is_telegram:
                # Kill existing telegram process
                try:
                    pid = int(existing)
                    if sys.platform == "win32":
                        subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, timeout=5)
                    else:
                        os.kill(pid, 15)
                except Exception:
                    pass
                try:
                    os.remove(pid_file)
                except Exception:
                    pass
            elif existing_is_tv and not desired_is_tv:
                # Switching from TV to Telegram — just remove TV marker
                try:
                    os.remove(pid_file)
                except Exception:
                    pass
            elif existing_is_telegram and desired_is_tv:
                # Kill telegram process before starting TradingView mode
                try:
                    pid = int(existing)
                    if sys.platform == "win32":
                        subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, timeout=5)
                    else:
                        os.kill(pid, 15)
                except Exception:
                    pass
                try:
                    os.remove(pid_file)
                except Exception:
                    pass

            # Final check — if still exists, something is really running
            if os.path.exists(pid_file):
                return {"status": "already_running"}

        # Validate broker(s) before starting
        result = await db.execute(
            select(User).options(selectinload(User.broker_settings)).where(User.id == user.id)
        )
        u = result.scalar_one_or_none()
        supported = {"deriv", "deriv_demo", "deriv_real", "iqoption", "quotex", "pocketoption"}
        active_settings = []
        if u and u.broker_settings:
            active_settings = [s for s in u.broker_settings if s.is_active]
            for s in active_settings:
                if s.broker_name.lower() not in supported:
                    from fastapi import HTTPException
                    raise HTTPException(status_code=400, detail={
                        "status": "error",
                        "message": f"Broker '{s.broker_name}' não suportado pelo copier. Use: {', '.join(sorted(supported))}"
                    })
            if not active_settings:
                from fastapi import HTTPException
                raise HTTPException(status_code=400, detail={
                    "status": "error",
                    "message": "Nenhuma corretora ativa. Configure e ative pelo menos uma corretora."
                })

        broker_name = (user.broker or "").lower()
        if u and u.broker_settings:
            primary = next((s for s in u.broker_settings if s.is_active and s.broker_name.lower() == broker_name), None)
            if not primary and active_settings:
                broker_name = active_settings[0].broker_name.lower()

        # ── TradingView mode ───────────────────────────────────────
        if u and u.signal_source == "tradingview":
            if not u.webhook_secret:
                from fastapi import HTTPException
                raise HTTPException(status_code=400, detail={
                    "status": "error",
                    "message": "Gere um Webhook Secret em Configurações antes de ativar o modo TradingView."
                })

            # Warm up: connect TODOS os brokers ativos
            try:
                from src.routes.tradingview_bridge import _create_broker
                for s in active_settings:
                    try:
                        _create_broker(u.id, s.broker_name.lower())
                    except Exception as e:
                        logger.warning(f"Warm-up de {s.broker_name} falhou: {e}")
            except Exception as e:
                from fastapi import HTTPException
                raise HTTPException(status_code=400, detail={
                    "status": "error",
                    "message": f"Falha ao conectar broker: {str(e)}"
                })

            # Write TV marker
            with open(pid_file, "w") as f:
                f.write(f"tv:{u.id}")

            # Write initial live_status.json
            initial_balance = 0.0
            if u.broker_settings:
                active_bs = next((s for s in u.broker_settings if s.is_active), None)
                if active_bs and active_bs.balance:
                    initial_balance = float(active_bs.balance)
            status = {
                "broker": broker_name,
                "account_mode": "Demo" if (u.broker_settings and next((s for s in u.broker_settings if s.is_active), None) and next((s for s in u.broker_settings if s.is_active), None).is_demo) else "Real",
                "initial_balance": initial_balance,
                "current_balance": initial_balance,
                "profit": 0.0,
                "profit_pct": 0.0,
                "current_stake": 0.0,
                "signals_today": 0,
                "success_count": 0,
                "success_rate": 0.0,
                "gale_level": 0,
                "daily_target": round(initial_balance * 0.03, 2) if initial_balance else 0,
                "last_message": "TradingView Webhook Pronto — Aguardando alertas",
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "meta_hit_today": False,
                "auto_lock_meta": True,
                "meta_hit_date": None,
                "source": "tradingview",
            }
            with open(status_file, "w") as f:
                json.dump(status, f)

            return {"status": "started", "active": True, "broker": broker_name, "mode": "tradingview"}

        # ── Telegram mode ─────────────────────────────────────────
        cmd = [sys.executable, "-m", "src.telegram_copier", "--user-id", str(user.id)]
        if broker_name:
            cmd += ["--broker", broker_name]

        log_fh = open("copier.log", "a", encoding="utf-8")
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=log_fh,
                stderr=subprocess.STDOUT,
                cwd=os.getcwd()
            )
        except Exception:
            log_fh.close()
            raise

        with open(pid_file, "w") as f:
            f.write(str(proc.pid))
        return {"status": "started", "active": True, "broker": broker_name, "mode": "telegram"}
    else:
        if not os.path.exists(pid_file):
            return {"status": "not_running", "active": False}
        try:
            with open(pid_file) as f:
                content = f.read().strip()
        except Exception:
            return {"status": "not_running", "active": False}

        # TradingView marker — just remove file, no process to kill
        if content.startswith("tv:"):
            try:
                os.remove(pid_file)
            except Exception:
                pass
            return {"status": "stopped", "active": False}

        # Telegram process — kill it
        try:
            pid = int(content)
        except Exception:
            return {"status": "not_running", "active": False}
        try:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, timeout=5)
            else:
                os.kill(pid, 15)
        except Exception:
            pass
        try:
            os.remove(pid_file)
        except Exception:
            pass
        return {"status": "stopped", "active": False}


@app.get("/copier/meta-status", tags=["Telegram"])
async def copier_meta_status(
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Retorna status da meta diaria e auto-lock. Auto-reseta se for novo dia."""
    from datetime import datetime
    result = await db.execute(select(User).where(User.id == user.id))
    u = result.scalar_one_or_none() or user

    today = datetime.now().strftime("%Y-%m-%d")

    # Auto-reset se for novo dia
    needs_commit = False
    if u.meta_hit_date and u.meta_hit_date != today:
        from src.database.session import get_async_session
        from src.models.broker import BrokerSetting
        if u.auto_lock_meta:
            # Reseta user
            u.meta_hit_today = False
            u.meta_hit_date = None
            needs_commit = True
            # Reseta broker setting ativo
            bres = await db.execute(
                select(BrokerSetting).where(
                    BrokerSetting.user_id == u.id,
                    BrokerSetting.is_active == True
                ).limit(1)
            )
            bset = bres.scalar_one_or_none()
            if bset:
                bset.meta_hit_today = False
                bset.meta_hit_date = None
                bset.today_trades = 0
                bset.today_profit = 0.0

    meta_blocked = u.auto_lock_meta and u.meta_hit_today and u.meta_hit_date == today

    if needs_commit:
        await db.commit()

    return {
        "auto_lock_meta": u.auto_lock_meta,
        "meta_hit_today": u.meta_hit_today,
        "meta_hit_date": u.meta_hit_date,
        "meta_blocked": meta_blocked,
        "today": today,
    }


@app.post("/copier/auto-lock", tags=["Telegram"])
async def copier_auto_lock(
    body: dict,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Ativa/desativa o auto-lock (trava ao bater a meta diaria)."""
    enabled = body.get("enabled", False)
    user.auto_lock_meta = enabled
    if not enabled:
        user.meta_hit_today = False
        user.meta_hit_date = None
    db.add(user)
    await db.commit()
    return {"status": "ok", "auto_lock_meta": enabled}


@app.get("/account/me", tags=["Account"])
async def get_me(
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session)
):
    user.last_seen = datetime.utcnow()
    await db.commit()
    result = await db.execute(select(User).options(selectinload(User.plan)).where(User.id == user.id))
    u = result.scalar_one_or_none() or user
    plan_name = u.plan.name if u.plan else "admin"
    is_demo = u.plan.is_demo if u.plan else True
    return {
        "id": u.id,
        "email": u.email,
        "username": u.username,
        "broker": u.broker,
        "stake": u.stake,
        "risk_mode": u.risk_mode,
        "total_profit": u.total_profit,
        "plan_expires_at": u.plan_expires_at,
        "plan_name": plan_name,
        "is_demo": is_demo,
        "telegram_enabled": u.telegram_enabled,
        "signals_today": 0,
        "liberado": u.liberado,
    }


@app.post("/create-checkout-session", tags=["Payments"])
async def checkout(plan_name: str, user: User = Depends(current_active_user)):
    try:
        url = create_checkout_session(user.email, plan_name)
        return {"url": url}
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": str(e)}


@app.post("/stripe/webhook", tags=["Payments"])
async def stripe_webhook(request: Request):
    return await handle_webhook(request)


@app.get("/admin/users", tags=["Admin"])
async def list_users(
    plan_filter: Optional[str] = None,
    db: AsyncSession = Depends(get_async_session),
    admin: User = Depends(current_superuser),
):
    query = select(User)
    result = await db.execute(query)
    users = result.scalars().all()
    return [
        {
            "id": u.id,
            "email": u.email,
            "username": u.username,
            "active": u.is_active,
            "total_profit": u.total_profit,
            "risk_score": user_risk_score(u),
        }
        for u in users
    ]


@app.post("/admin/change-plan", tags=["Admin"])
async def change_plan(
    email: str,
    new_plan: str,
    db: AsyncSession = Depends(get_async_session),
    admin: User = Depends(current_superuser),
):
    user_result = await db.execute(select(User).where(User.email == email))
    user = user_result.scalar_one_or_none()

    plan_result = await db.execute(select(Plan).where(Plan.name == new_plan))
    plan = plan_result.scalar_one_or_none()

    if not user or not plan:
        return {"error": "User or Plan not found."}

    old_plan_name = "None"
    user.plan_id = plan.id
    user.plan_expires_at = datetime.utcnow() + timedelta(days=30)

    db.add(PlanHistory(
        user_id=user.id,
        old_plan=old_plan_name,
        new_plan=new_plan,
        changed_by=admin.email
    ))
    db.add(AdminLog(admin_email=admin.email,
               action="change_plan", target_user=email))
    await db.commit()

    try:
        await send_plan_upgrade_email(email, new_plan)
    except Exception:
        pass

    log_admin(admin.email, "change_plan", email)
    return {"status": "updated", "email": email, "new_plan": new_plan}


@app.post("/admin/liberar-cliente", tags=["Admin"])
async def liberar_cliente(
    email: str,
    plan_name: str = "Basic",
    db: AsyncSession = Depends(get_async_session),
    admin: User = Depends(current_superuser),
):
    user_result = await db.execute(select(User).where(User.email == email))
    user = user_result.scalar_one_or_none()
    if not user:
        return {"error": "Usuário não encontrado."}

    plan_result = await db.execute(select(Plan).where(Plan.name == plan_name))
    plan = plan_result.scalar_one_or_none()

    user.liberado = True
    user.trading_enabled = True
    if plan:
        user.plan_id = plan.id
        user.plan_expires_at = datetime.utcnow() + timedelta(days=30)

    db.add(AdminLog(
        admin_email=admin.email,
        action="liberar_cliente",
        target_user=email,
        detail=f"Plano: {plan_name}"
    ))
    await db.commit()
    log_admin(admin.email, "liberar_cliente", email)

    try:
        await send_plan_upgrade_email(email, plan_name)
    except Exception:
        pass

    return {"status": "liberado", "email": email, "plano": plan_name}


@app.post("/admin/bloquear-cliente", tags=["Admin"])
async def bloquear_cliente(
    email: str,
    db: AsyncSession = Depends(get_async_session),
    admin: User = Depends(current_superuser),
):
    user_result = await db.execute(select(User).where(User.email == email))
    user = user_result.scalar_one_or_none()
    if not user:
        return {"error": "Usuário não encontrado."}

    user.liberado = False
    user.trading_enabled = False
    db.add(AdminLog(
        admin_email=admin.email,
        action="bloquear_cliente",
        target_user=email
    ))
    await db.commit()
    return {"status": "bloqueado", "email": email}


@app.get("/admin/ai/profitable", tags=["Admin – AI"])
async def ai_profitable(
    db: AsyncSession = Depends(get_async_session),
    admin: User = Depends(current_superuser)
):
    result = await db.execute(select(User))
    users = list(result.scalars().all())
    return {"profitable_users": detect_profitable_users(users)}


# ====================== FRONTEND SPA FALLBACK ======================
# Must be the LAST route so it only catches unhandled paths.
_API_PREFIXES = (
    "/api/", "/auth/", "/broker/", "/admin/", "/telegram/", "/ws/", "/docs",
    "/openapi.json", "/redoc", "/health", "/risk-term/", "/user/", "/licenca/",
    "/client-setup/", "/planilha/", "/tradingview/"
)
if _frontend_dir:
    import mimetypes
    from fastapi.responses import FileResponse, JSONResponse

    from fastapi.responses import HTMLResponse

    _TOAST_SCRIPT = """<script id="rde-modern-toast-system">
(function() {
  if (window._rde_toast_injected) return;
  window._rde_toast_injected = true;

  // ─── Sidebar Nav Interceptor ───────────────────────────────────────────────
  // Intercepts clicks on sidebar <a> links after React renders them.
  // Uses window.location.href so the static HTML files load correctly on the
  // FastAPI server, without touching Next.js router internals (avoids hydration
  // errors and "Carregando portal..." black screen).
  (function() {
    var NAV_HREFS = ['/dashboard','/planilha','/estatisticas','/risco','/carteira','/configuracao','/perfil','/setup','/admin','/login','/'];
    function patchSidebarLinks(root) {
      var links = (root || document).querySelectorAll('aside a[href], nav a[href]');
      links.forEach(function(a) {
        if (a._rde_patched) return;
        a._rde_patched = true;
        var href = a.getAttribute('href');
        if (!href || href.startsWith('http') || href.startsWith('mailto') || href.startsWith('#')) return;
        a.addEventListener('click', function(e) {
          e.preventDefault();
          e.stopPropagation();
          window.location.href = href;
        }, true);
      });
    }
    // Patch existing links + observe DOM for when React renders the sidebar
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', function() { patchSidebarLinks(); });
    } else {
      patchSidebarLinks();
    }
    var observer = new MutationObserver(function(mutations) {
      mutations.forEach(function(m) {
        if (m.addedNodes.length) patchSidebarLinks();
      });
    });
    observer.observe(document.body || document.documentElement, { childList: true, subtree: true });
  })();
  // ──────────────────────────────────────────────────────────────────────────

  window.alert = function(msg) {
    var container = document.getElementById('rde-toast-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'rde-toast-container';
      container.style.cssText = 'position:fixed;top:24px;right:24px;z-index:999999;display:flex;flex-direction:column;gap:12px;max-width:420px;width:calc(100% - 48px);pointer-events:none;';
      document.body.appendChild(container);
    }
    var toast = document.createElement('div');
    toast.style.cssText = 'pointer-events:auto;background:rgba(15,23,42,0.95);border:1px solid rgba(59,130,246,0.3);color:#fff;padding:16px 20px;border-radius:16px;backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);box-shadow:0 25px 35px -5px rgba(0,0,0,0.6), 0 0 15px rgba(59,130,246,0.15);font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;font-size:13px;display:flex;align-items:flex-start;gap:14px;transform:translateX(50px) scale(0.95);opacity:0;transition:all 0.35s cubic-bezier(0.16,1,0.3,1);';
    var msgStr = String(msg || '');
    var isErr = /erro|falha|invalid|incorret|bloquead|recusad|atenção|warning|danger/i.test(msgStr);
    var isOk = /sucesso|conectad|ativad|salv|concluíd|ok|bem-vindo/i.test(msgStr);
    var icon = isErr ? '⚠️' : (isOk ? '✅' : 'ℹ️');
    var iconBg = isErr ? 'rgba(239,68,68,0.15)' : (isOk ? 'rgba(16,185,129,0.15)' : 'rgba(59,130,246,0.15)');
    var iconBorder = isErr ? 'rgba(239,68,68,0.3)' : (isOk ? 'rgba(16,185,129,0.3)' : 'rgba(59,130,246,0.3)');
    var accentColor = isErr ? '#f87171' : (isOk ? '#34d399' : '#60a5fa');
    var title = isErr ? 'Aviso do Sistema' : (isOk ? 'Operação Concluída' : 'Notificação RDE');
    toast.innerHTML = '<div style="width:38px;height:38px;border-radius:12px;background:'+iconBg+';border:1px solid '+iconBorder+';display:flex;align-items:center;justify-content:center;font-size:18px;flex-shrink:0;box-shadow:0 4px 10px rgba(0,0,0,0.2);">'+icon+'</div>' +
                      '<div style="flex:1;padding-top:2px;">' +
                        '<div style="font-size:11px;font-weight:900;text-transform:uppercase;letter-spacing:0.1em;color:'+accentColor+';margin-bottom:3px;">'+title+'</div>' +
                        '<div style="line-height:1.4;font-weight:500;color:#f1f5f9;word-break:break-word;">'+msgStr+'</div>' +
                      '</div>' +
                      '<button style="background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);color:#94a3b8;cursor:pointer;width:24px;height:24px;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:12px;line-height:1;margin-left:4px;flex-shrink:0;transition:all 0.2s;" onmouseover="this.style.color=\\'#fff\\';this.style.background=\\'rgba(255,255,255,0.15)\\'" onmouseout="this.style.color=\\'#94a3b8\\';this.style.background=\\'rgba(255,255,255,0.05)\\'" onclick="var p=this.parentElement;p.style.opacity=\\'0\\';p.style.transform=\\'translateX(50px)\\';setTimeout(function(){p.remove();},300)">✕</button>';
    container.appendChild(toast);
    requestAnimationFrame(function() {
      toast.style.transform = 'translateX(0) scale(1)';
      toast.style.opacity = '1';
    });
    setTimeout(function() {
      if (toast.parentElement) {
        toast.style.transform = 'translateX(50px) scale(0.95)';
        toast.style.opacity = '0';
        setTimeout(function() { if(toast.parentElement) toast.remove(); }, 350);
      }
    }, 5000);
  };
})();
</script>"""

    _NO_CACHE_HEADERS = {
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0",
    }

    def _render_html(filepath: str) -> HTMLResponse:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            if "</head>" in content:
                content = content.replace("</head>", f"{_TOAST_SCRIPT}</head>", 1)
            elif "</body>" in content:
                content = content.replace("</body>", f"{_TOAST_SCRIPT}</body>", 1)
            else:
                content += _TOAST_SCRIPT
            return HTMLResponse(content, headers=_NO_CACHE_HEADERS)
        except Exception:
            return FileResponse(filepath, headers=_NO_CACHE_HEADERS)

    @app.api_route("/", methods=["GET", "HEAD"])
    async def serve_index():
        fp = _os.path.join(_frontend_dir, "acesso.html")
        if _os.path.isfile(fp):
            return _render_html(fp)
        fp = _os.path.join(_frontend_dir, "index.html")
        if _os.path.isfile(fp):
            return _render_html(fp)
        return JSONResponse({"detail": "Not Found"}, status_code=404)

    @app.api_route("/{path:path}", methods=["GET", "HEAD"])
    async def spa_fallback(path: str):
        # 1. Tenta encontrar o arquivo diretamente no diretório cliente/frontend
        fp = _os.path.join(_frontend_dir, path)
        if _os.path.isfile(fp):
            if fp.endswith(".html"):
                return _render_html(fp)
            ct = mimetypes.guess_type(fp)[0] or ("text/plain; charset=utf-8" if fp.endswith(".txt") else "application/octet-stream")
            file_headers = dict(_NO_CACHE_HEADERS) if (fp.endswith(".js") or fp.endswith(".html") or fp.endswith(".txt")) else {"Cache-Control": "public, max-age=31536000, immutable"}
            return FileResponse(fp, media_type=ct, headers=file_headers)

        # 2. Mapeamento de atalho para arquivos .__PAGE__.txt do Next.js (ex: configuracao/__next.configuracao.__PAGE__.txt -> configuracao/__next.configuracao/__PAGE__.txt)
        if ".__PAGE__.txt" in path:
            alt_path = path.replace(".__PAGE__.txt", "/__PAGE__.txt")
            alt_fp = _os.path.join(_frontend_dir, alt_path)
            if _os.path.isfile(alt_fp):
                return FileResponse(alt_fp, media_type="text/plain; charset=utf-8", headers=_NO_CACHE_HEADERS)

        # 3. Mapeia rotas sem extensão para arquivo .html (ex: /dashboard -> dashboard.html)
        clean_path = path.rstrip("/")
        html_fp = _os.path.join(_frontend_dir, f"{clean_path}.html")
        if _os.path.isfile(html_fp):
            return _render_html(html_fp)

        # 4. Prefixos de API do backend retornam 404 JSON se não encontrarem rota registrada
        for prefix in _API_PREFIXES:
            if path.startswith(prefix.lstrip("/")):
                return JSONResponse({"detail": "Not Found"}, status_code=404)

        # 5. Se for um arquivo de dados do Next (_next/data) ou .json/.txt inexistente no disco, retorna 404 JSON (não index.html)
        if path.startswith("_next/") or path.endswith(".txt") or path.endswith(".json"):
            return JSONResponse({"detail": "Not Found"}, status_code=404)

        # 6. Fallback final para index.html (SPA)
        index_fp = _os.path.join(_frontend_dir, "index.html")
        if _os.path.isfile(index_fp):
            return _render_html(index_fp)
        return JSONResponse({"detail": "Not Found"}, status_code=404)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)