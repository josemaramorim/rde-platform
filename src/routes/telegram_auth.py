from __future__ import annotations

import asyncio
import logging
import os
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError, PhoneCodeExpiredError, PhoneCodeInvalidError
from sqlalchemy.ext.asyncio import AsyncSession
from src.database.session import get_async_db
from src.core.config import settings
from src.auth.users import current_active_user
from src.models.user import User

logger = logging.getLogger("rde")

router = APIRouter(prefix="/telegram", tags=["Telegram Auth"])

API_ID = settings.TELEGRAM_API_ID or 24906269
API_HASH = settings.TELEGRAM_API_HASH or "4826f9dd0be48b617f94fc04b88ffabc"



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


def _update_user_live_status(user_id, message: str, is_error: bool = False):
    import json
    from datetime import datetime
    status_file = f"live_status_{user_id}.json"
    status_data = {}
    if os.path.exists(status_file):
        try:
            with open(status_file, "r", encoding="utf-8") as sf:
                status_data = json.load(sf)
        except Exception:
            status_data = {}

    status_data["last_message"] = message
    status_data["timestamp"] = datetime.now().strftime("%H:%M:%S")
    try:
        with open(status_file, "w", encoding="utf-8") as sf:
            json.dump(status_data, sf, ensure_ascii=False)
    except Exception:
        pass

    try:
        with open("copier.log", "a", encoding="utf-8") as lf:
            prefix = "ERROR" if is_error else "INFO"
            lf.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S,%f')[:-3]} - {prefix} - [TELEGRAM AUTH] {message}\n")
    except Exception:
        pass


_user_locks: dict[str, asyncio.Lock] = {}
_temp_user_sessions: dict[str, str] = {}

def _get_user_lock(user_id) -> asyncio.Lock:
    uid = str(user_id)
    if uid not in _user_locks:
        _user_locks[uid] = asyncio.Lock()
    return _user_locks[uid]


def _create_client(user_id: int):
    return TelegramClient(_session_name(user_id), API_ID, API_HASH, system_version="4.16.30-vxRDE")


@router.get("/auth-status")
async def telegram_auth_status(user: User = Depends(current_active_user)):
    user_lock = _get_user_lock(user.id)
    if user_lock.locked():
        return {"authenticated": False, "message": "Operação em andamento"}
    
    async with user_lock:
        client = _create_client(user.id)
        try:
            await asyncio.wait_for(client.connect(), timeout=5.0)
            authorized = await client.is_user_authorized()
            me = await client.get_me() if authorized else None
            return {
                "authenticated": authorized,
                "phone": getattr(me, "phone", None) or user.telegram_phone,
                "username": getattr(me, "username", None),
            }
        except Exception as e:
            logger.error(f"Erro ao verificar status de autenticacao: {e}")
            return {"authenticated": False, "error": str(e)}
        finally:
            try:
                await asyncio.wait_for(client.disconnect(), timeout=3.0)
            except Exception:
                pass


@router.post("/send-code")
async def telegram_send_code(
    req: SendCodeRequest, 
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_db)
):
    user_lock = _get_user_lock(user.id)
    async with user_lock:
        phone = req.phone.strip()
        if not phone.startswith("+"):
            phone = f"+{phone}"

        # Persiste o número dinâmico do usuário no banco de dados
        user.telegram_phone = phone
        db.add(user)
        try:
            await db.commit()
        except Exception as db_err:
            logger.warning(f"Erro ao gravar telegram_phone no BD: {db_err}")

        _cleanup_session(user.id)
        client = _create_client(user.id)

        try:
            await asyncio.wait_for(client.connect(), timeout=10.0)
            if await client.is_user_authorized():
                _update_user_live_status(user.id, f"Telegram já autenticado ({phone}).")
                return {"status": "already_authorized", "message": "Já autenticado no Telegram"}
            sent = await asyncio.wait_for(client.send_code_request(phone), timeout=12.0)
            _update_user_live_status(user.id, f"Código enviado para Telegram ({phone}). Digite o código no Dashboard.")
            return {
                "status": "code_sent",
                "message": "Código enviado para seu Telegram",
                "phone_code_hash": sent.phone_code_hash,
            }
        except Exception as e:
            err_msg = str(e)
            logger.error(f"Erro ao enviar código Telegram: {err_msg}")
            if "invalid" in err_msg.lower() or "phone" in err_msg.lower():
                detail = "Número de telefone inválido. Verifique se incluiu o DDD (Exemplo: +5511999999999)"
            elif "flood" in err_msg.lower():
                detail = "Muitas tentativas em pouco tempo. Aguarde alguns minutos e tente novamente."
            else:
                detail = f"Falha no Telegram: {err_msg}"
            _update_user_live_status(user.id, f"Erro no envio de código: {detail}", is_error=True)
            raise HTTPException(status_code=400, detail=detail)
        finally:
            try:
                await asyncio.wait_for(client.disconnect(), timeout=3.0)
            except Exception:
                pass


@router.post("/sign-in")
async def telegram_sign_in(
    req: SignInRequest, 
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_db)
):
    user_lock = _get_user_lock(user.id)
    async with user_lock:
        client = _create_client(user.id)

        phone = req.phone.strip()
        if not phone.startswith("+"):
            phone = f"+{phone}"

        # Persiste o número dinâmico do usuário no banco de dados
        user.telegram_phone = phone
        db.add(user)
        try:
            await db.commit()
        except Exception as db_err:
            logger.warning(f"Erro ao gravar telegram_phone no BD no sign-in: {db_err}")

        try:
            await asyncio.wait_for(client.connect(), timeout=10.0)
            if await client.is_user_authorized():
                _update_user_live_status(user.id, f"Telegram já autenticado ({phone}).")
                return {"status": "already_authorized", "message": "Já autenticado no Telegram"}

            try:
                if req.phone_code_hash:
                    await client.sign_in(phone, req.code, phone_code_hash=req.phone_code_hash)
                else:
                    await client.sign_in(phone, req.code)
            except SessionPasswordNeededError:
                if not req.password:
                    _update_user_live_status(user.id, "Senha 2FA necessária para o Telegram.")
                    return {"status": "password_needed", "message": "Senha 2FA necessária"}
                await client.sign_in(password=req.password)

            me = await client.get_me()
            _update_user_live_status(user.id, f"Telegram autenticado com sucesso ({phone})! Clique em ATIVAR COPIER.")
            return {
                "status": "success",
                "message": "Autenticado com sucesso no Telegram!",
                "phone": getattr(me, "phone", None),
                "username": getattr(me, "username", None),
            }
        except PhoneCodeExpiredError:
            _update_user_live_status(user.id, "Erro no Telegram: Código expirado.", is_error=True)
            return {"status": "code_expired", "message": "Código expirado. Solicite um novo."}
        except PhoneCodeInvalidError:
            _update_user_live_status(user.id, "Erro no Telegram: Código inválido.", is_error=True)
            return {"status": "code_invalid", "message": "Código inválido. Tente novamente."}
        except Exception as e:
            err_msg = str(e)
            logger.error(f"Erro ao autenticar Telegram: {err_msg}")
            _update_user_live_status(user.id, f"Erro na autenticação Telegram: {err_msg}", is_error=True)
            raise HTTPException(status_code=400, detail=err_msg)
        finally:
            try:
                await asyncio.wait_for(client.disconnect(), timeout=3.0)
            except Exception:
                pass


@router.post("/logout")
async def telegram_logout(user: User = Depends(current_active_user)):
    user_lock = _get_user_lock(user.id)
    async with user_lock:
        client = _create_client(user.id)
        try:
            await asyncio.wait_for(client.connect(), timeout=5.0)
            if await client.is_user_authorized():
                await client.log_out()
        except Exception as e:
            logger.warning(f"Erro ao deslogar Telegram: {e}")
        finally:
            try:
                await asyncio.wait_for(client.disconnect(), timeout=3.0)
            except Exception:
                pass
        _cleanup_session(user.id)
        _update_user_live_status(user.id, "Telegram desconectado com sucesso.")
        return {"status": "logged_out", "message": "Desconectado do Telegram com sucesso"}
