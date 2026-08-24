from __future__ import annotations

import asyncio
import logging
import os
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, PhoneCodeExpiredError, PhoneCodeInvalidError
from src.core.config import settings
from src.auth.users import current_active_user
from src.models.user import User

logger = logging.getLogger("rde")

router = APIRouter(prefix="/telegram", tags=["Telegram Auth"])

API_ID = settings.TELEGRAM_API_ID or 24906269
API_HASH = settings.TELEGRAM_API_HASH or "4826f9dd0be48b617f94fc04b88ffabc"

# Lock para serializar acesso ao arquivo de sessao SQLite do Telethon
_session_lock = asyncio.Lock()


class SendCodeRequest(BaseModel):
    phone: str


class SignInRequest(BaseModel):
    phone: str
    code: str
    phone_code_hash: str | None = None
    password: str | None = None


def _session_name(user_id: int) -> str:
    return f"rde_user_session_{user_id}"


def _cleanup_session(user_id: int):
    base = _session_name(user_id)
    for f in [f"{base}.session-journal", f"{base}.session-shm", f"{base}.session-wal"]:
        if os.path.exists(f):
            try:
                os.remove(f)
            except Exception:
                pass


def _create_client(user_id: int):
    return TelegramClient(_session_name(user_id), API_ID, API_HASH, system_version="4.16.30-vxRDE")


@router.get("/auth-status")
async def telegram_auth_status(user: User = Depends(current_active_user)):
    async with _session_lock:
        _cleanup_session(user.id)
        client = _create_client(user.id)
        try:
            await client.connect()
            authorized = await client.is_user_authorized()
            me = await client.get_me() if authorized else None
            return {
                "authenticated": authorized,
                "phone": me.phone if me else None,
                "username": me.username if me else None,
            }
        except Exception as e:
            logger.error(f"Erro ao verificar status de autenticacao: {e}")
            return {"authenticated": False, "error": str(e)}
        finally:
            try:
                await client.disconnect()
            except Exception:
                pass


@router.post("/send-code")
async def telegram_send_code(req: SendCodeRequest, user: User = Depends(current_active_user)):
    async with _session_lock:
        _cleanup_session(user.id)
        client = _create_client(user.id)
        try:
            await client.connect()
            if await client.is_user_authorized():
                return {"status": "already_authorized", "message": "Ja autenticado"}
            sent = await client.send_code_request(req.phone)
            return {
                "status": "code_sent",
                "message": "Codigo enviado para seu Telegram",
                "phone_code_hash": sent.phone_code_hash,
            }
        except Exception as e:
            logger.error(f"Erro ao enviar codigo: {e}")
            raise HTTPException(status_code=400, detail=str(e))
        finally:
            try:
                await client.disconnect()
            except Exception:
                pass


@router.post("/sign-in")
async def telegram_sign_in(req: SignInRequest, user: User = Depends(current_active_user)):
    async with _session_lock:
        _cleanup_session(user.id)
        client = _create_client(user.id)
        try:
            await client.connect()
            if await client.is_user_authorized():
                return {"status": "already_authorized", "message": "Ja autenticado"}

            try:
                if req.phone_code_hash:
                    await client.sign_in(req.phone, req.code, phone_code_hash=req.phone_code_hash)
                else:
                    await client.sign_in(req.phone, req.code)
            except SessionPasswordNeededError:
                if not req.password:
                    return {"status": "password_needed", "message": "Senha 2FA necessaria"}
                await client.sign_in(password=req.password)

            phone = None
            username = None
            try:
                me = await client.get_me()
                phone = me.phone
                username = me.username
            except Exception as e:
                logger.warning(f"Nao foi possivel obter dados do usuario: {e}")

            return {
                "status": "success",
                "message": "Autenticado com sucesso",
                "phone": phone,
                "username": username,
            }
        except PhoneCodeExpiredError:
            return {"status": "code_expired", "message": "Codigo expirado. Solicite um novo."}
        except PhoneCodeInvalidError:
            return {"status": "code_invalid", "message": "Codigo invalido. Tente novamente."}
        except Exception as e:
            logger.error(f"Erro ao autenticar: {e}")
            raise HTTPException(status_code=400, detail=str(e))
        finally:
            try:
                await client.disconnect()
            except Exception as e:
                logger.warning(f"Erro ao desconectar cliente Telegram: {e}")


@router.post("/logout")
async def telegram_logout(user: User = Depends(current_active_user)):
    async with _session_lock:
        client = _create_client(user.id)
        try:
            await client.connect()
            if await client.is_user_authorized():
                await client.log_out()
        except Exception:
            pass
        finally:
            try:
                await client.disconnect()
            except Exception:
                pass
        _cleanup_session(user.id)
        return {"status": "logged_out", "message": "Desconectado do Telegram"}
