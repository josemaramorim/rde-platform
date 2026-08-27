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


def _create_client(session_str: str | None = None):
    session = StringSession(session_str) if session_str else StringSession()
    return TelegramClient(session, API_ID, API_HASH, system_version="4.16.30-vxRDE")


@router.get("/auth-status")
async def telegram_auth_status(
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_db)
):
    user_lock = _get_user_lock(user.id)
    if user_lock.locked():
        return {"authenticated": False, "message": "Operação em andamento"}
    
    async with user_lock:
        session_str = user.telegram_session_string
        if not session_str:
            db_phone = user.telegram_phone.lstrip("+") if user.telegram_phone else None
            return {"authenticated": False, "phone": db_phone}

        client = _create_client(session_str)
        try:
            await asyncio.wait_for(client.connect(), timeout=10.0)
            authorized = await client.is_user_authorized()
            if authorized:
                me = await client.get_me()
                me_phone = me.phone.lstrip("+") if (me and me.phone) else (user.telegram_phone.lstrip("+") if user.telegram_phone else None)
                return {
                    "authenticated": True,
                    "phone": me_phone,
                    "username": getattr(me, "username", None),
                }
            else:
                user.telegram_session_string = None
                db.add(user)
                await db.commit()
                _update_user_live_status(user.id, "Sessão Telegram revogada. Solicite novo código.", is_error=True)
                return {"authenticated": False, "phone": user.telegram_phone}
        except Exception as e:
            logger.warning(f"Sessão Telegram inválida/expirada: {e}")
            user.telegram_session_string = None
            db.add(user)
            await db.commit()
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
        phone_digits = req.phone.strip().lstrip("+")
        phone_full = f"+{phone_digits}"

        user.telegram_phone = phone_digits
        db.add(user)
        try:
            await db.commit()
        except Exception as db_err:
            logger.warning(f"Erro ao gravar telegram_phone no BD: {db_err}")

        # Se ja possui StringSession valida salva no banco
        if user.telegram_session_string:
            try:
                test_client = _create_client(user.telegram_session_string)
                await asyncio.wait_for(test_client.connect(), timeout=10.0)
                if await test_client.is_user_authorized():
                    await test_client.disconnect()
                    _update_user_live_status(user.id, f"Telegram já autenticado ({phone_digits}).")
                    return {"status": "already_authorized", "message": "Já autenticado no Telegram"}
                await test_client.disconnect()
            except Exception:
                user.telegram_session_string = None
                db.add(user)
                await db.commit()

        # Cria nova StringSession limpa em memória para receber o código
        client = _create_client()

        try:
            await asyncio.wait_for(client.connect(), timeout=25.0)
            sent = await asyncio.wait_for(client.send_code_request(phone_full), timeout=30.0)
            
            # Salva o progresso temporario da StringSession
            _temp_user_sessions[str(user.id)] = client.session.save()
            
            _update_user_live_status(user.id, f"Código enviado para Telegram ({phone_digits}). Digite o código no Dashboard.")
            return {
                "status": "code_sent",
                "message": "Código enviado para seu Telegram",
                "phone_code_hash": sent.phone_code_hash,
            }
        except asyncio.TimeoutError:
            detail = "O Telegram demorou para responder na conexão inicial. Tente clicar em Enviar Código novamente."
            logger.warning(f"Timeout ao conectar/enviar código Telegram para {phone_digits}")
            _update_user_live_status(user.id, f"Erro no envio de código: {detail}", is_error=True)
            raise HTTPException(status_code=400, detail=detail)
        except Exception as e:
            err_msg = str(e)
            logger.error(f"Erro ao enviar código Telegram: {err_msg}")
            if "invalid" in err_msg.lower() or "phone" in err_msg.lower():
                detail = "Número de telefone inválido. Verifique se incluiu o DDD (Exemplo: 5511999999999)"
            elif "flood" in err_msg.lower():
                detail = "Muitas tentativas em pouco tempo. Aguarde alguns minutos e tente novamente."
            else:
                detail = f"Falha no Telegram: {err_msg}"
            _update_user_live_status(user.id, f"Erro no envio de código: {detail}", is_error=True)
            raise HTTPException(status_code=400, detail=detail)
        finally:
            try:
                await asyncio.wait_for(client.disconnect(), timeout=5.0)
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
        phone_digits = req.phone.strip().lstrip("+")
        phone_full = f"+{phone_digits}"

        user.telegram_phone = phone_digits
        db.add(user)
        try:
            await db.commit()
        except Exception as db_err:
            logger.warning(f"Erro ao gravar telegram_phone no BD no sign-in: {db_err}")

        # Recupera a StringSession temporaria iniciada no send-code
        temp_session = _temp_user_sessions.get(str(user.id))
        client = _create_client(temp_session)

        try:
            await asyncio.wait_for(client.connect(), timeout=25.0)
            if await client.is_user_authorized():
                saved_session = client.session.save()
                user.telegram_session_string = saved_session
                db.add(user)
                await db.commit()
                _update_user_live_status(user.id, f"Telegram já autenticado ({phone_digits}).")
                return {"status": "already_authorized", "message": "Já autenticado no Telegram"}

            try:
                if req.phone_code_hash:
                    await client.sign_in(phone_full, req.code, phone_code_hash=req.phone_code_hash)
                else:
                    await client.sign_in(phone_full, req.code)
            except SessionPasswordNeededError:
                if not req.password:
                    _temp_user_sessions[str(user.id)] = client.session.save()
                    _update_user_live_status(user.id, "Senha 2FA necessária para o Telegram.")
                    return {"status": "password_needed", "message": "Senha 2FA necessária"}
                await client.sign_in(password=req.password)

            # SUCESSO! Salva a StringSession no banco de dados permanentemente
            saved_session = client.session.save()
            user.telegram_session_string = saved_session
            db.add(user)
            await db.commit()
            _temp_user_sessions.pop(str(user.id), None)

            me = await client.get_me()
            me_phone = me.phone.lstrip("+") if (me and me.phone) else phone_digits
            _update_user_live_status(user.id, f"Telegram autenticado com sucesso ({me_phone})! Clique em ATIVAR COPIER.")
            return {
                "status": "success",
                "message": "Autenticado com sucesso no Telegram!",
                "phone": me_phone,
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
                await asyncio.wait_for(client.disconnect(), timeout=5.0)
            except Exception:
                pass


@router.post("/logout")
async def telegram_logout(
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_db)
):
    user_lock = _get_user_lock(user.id)
    async with user_lock:
        if user.telegram_session_string:
            client = _create_client(user.telegram_session_string)
            try:
                await asyncio.wait_for(client.connect(), timeout=10.0)
                if await client.is_user_authorized():
                    await client.log_out()
            except Exception as e:
                logger.warning(f"Erro ao deslogar Telegram: {e}")
            finally:
                try:
                    await asyncio.wait_for(client.disconnect(), timeout=3.0)
                except Exception:
                    pass
        
        user.telegram_session_string = None
        db.add(user)
        await db.commit()
        return {"status": "logged_out", "message": "Desconectado do Telegram com sucesso"}
