"""Rotas de licenciamento: tokens, ativação, validação."""
from __future__ import annotations
import os as _os
from typing import Optional
from datetime import datetime, timedelta
import hashlib
import httpx as _httpx
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select, func as sa_func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.users import fastapi_users, current_active_user, current_superuser
from src.models.user import User, Plan, AdminLog
from src.models.token_licenca import TokenLicenca
from src.database.session import get_async_session
from src.core.config import settings

router = APIRouter(tags=["Licenciamento"])


# ===================== MODELOS =====================

class AtivarTokenRequest(BaseModel):
    codigo: str

class GerarTokenRequest(BaseModel):
    plano: str = "Basic"
    quantidade: int = 1
    expiracao_dias: int = 30
    destinatario: Optional[str] = None

class LicencaValidateRequest(BaseModel):
    codigo: str
    cliente_email: str = ""

class LicencaValidateResponse(BaseModel):
    valido: bool
    plano: str = ""
    expiracao_dias: int = 0
    mensagem: str = ""

class TokenResponse(BaseModel):
    id: int
    codigo: str
    plano: str
    status: str
    expiracao_dias: int
    criado_em: str
    usado_por: Optional[str] = None
    usado_em: Optional[str] = None
    expira_em: Optional[str] = None
    ultima_atividade: Optional[str] = None
    ultimo_ip: Optional[str] = None


# ===================== DEPENDÊNCIA DE VALIDAÇÃO =====================

async def verificar_licenca(
    request: Request,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Verifica se o usuário tem licença válida. Admin sempre passa."""
    if user.is_superuser or user.is_admin:
        return user

    if not user.liberado:
        raise HTTPException(status_code=403, detail="Acesso negado. Conta não liberada pelo administrador.")

    if user.plan_expires_at and datetime.utcnow() > user.plan_expires_at:
        raise HTTPException(status_code=403, detail="Licença expirada. Renove seu plano.")

    # Atualiza último acesso no token, se houver
    result = await db.execute(
        select(TokenLicenca).where(TokenLicenca.usado_por == user.id)
    )
    token = result.scalar_one_or_none()
    if token:
        token.ultima_atividade = datetime.utcnow()
        token.ultimo_ip = request.client.host if request.client else None
        await db.commit()

    return user


# ===================== ENDPOINTS ADMIN =====================

@router.post("/admin/tokens/gerar", tags=["Admin"])
async def gerar_tokens(
    body: GerarTokenRequest,
    admin: User = Depends(current_superuser),
    db: AsyncSession = Depends(get_async_session),
):
    """Gera um ou mais tokens de licença."""
    tokens = []
    for _ in range(body.quantidade):
        token = TokenLicenca(
            codigo=TokenLicenca.gerar_codigo(),
            plano=body.plano,
            expiracao_dias=body.expiracao_dias,
            criado_por=admin.email,
            destinatario=body.destinatario.strip().lower() if body.destinatario else None,
        )
        db.add(token)
        tokens.append(token.codigo)

    db.add(AdminLog(
        admin_email=admin.email,
        action="gerar_tokens",
        detail=f"{body.quantidade}x {body.plano} ({body.expiracao_dias}d)"
    ))
    await db.commit()

    return {"status": "ok", "quantidade": body.quantidade, "plano": body.plano, "tokens": tokens}


@router.get("/admin/tokens", tags=["Admin"])
async def listar_tokens(
    plano: Optional[str] = None,
    status: Optional[str] = None,
    admin: User = Depends(current_superuser),
    db: AsyncSession = Depends(get_async_session),
):
    """Lista todos os tokens com filtros opcionais."""
    query = select(TokenLicenca).options(selectinload(TokenLicenca.usuario)).order_by(TokenLicenca.created_at.desc())

    if plano:
        query = query.where(TokenLicenca.plano == plano)
    if status == "disponivel":
        query = query.where(TokenLicenca.usado_por.is_(None), TokenLicenca.revogado.is_(False))
    elif status == "ativo":
        query = query.where(TokenLicenca.usado_por.isnot(None), TokenLicenca.revogado.is_(False))
    elif status == "revogado":
        query = query.where(TokenLicenca.revogado.is_(True))
    elif status == "expirado":
        query = query.where(TokenLicenca.usado_por.isnot(None), TokenLicenca.revogado.is_(False))

    result = await db.execute(query)
    tokens = result.scalars().all()

    # Filtro de expirado manual (não dá pra fazer no SQL com SQLite fácil)
    if status == "expirado":
        tokens = [t for t in tokens if t.expirado]

    return [
        {
            "id": t.id,
            "codigo": t.codigo[:12] + "..." if t.usado_por else t.codigo,
            "codigo_completo": t.codigo if not t.usado_por else None,
            "plano": t.plano,
            "status": t.status,
            "expiracao_dias": t.expiracao_dias,
            "criado_em": t.created_at.isoformat() if t.created_at else None,
            "usado_por": t.usuario.email if t.usuario else None,
            "usado_em": t.usado_em.isoformat() if t.usado_em else None,
            "expira_em": t.expira_em.isoformat() if t.expira_em else None,
            "ultima_atividade": t.ultima_atividade.isoformat() if t.ultima_atividade else None,
            "ultimo_ip": t.ultimo_ip,
            "destinatario": t.destinatario,
        }
        for t in tokens
    ]


@router.post("/admin/tokens/{token_id}/revogar", tags=["Admin"])
async def revogar_token(
    token_id: int,
    admin: User = Depends(current_superuser),
    db: AsyncSession = Depends(get_async_session),
):
    """Revoga um token de licença."""
    result = await db.execute(
        select(TokenLicenca).options(selectinload(TokenLicenca.usuario)).where(TokenLicenca.id == token_id)
    )
    token = result.scalar_one_or_none()
    if not token:
        raise HTTPException(status_code=404, detail="Token não encontrado.")

    token.revogado = True
    token.revogado_em = datetime.utcnow()
    token.revogado_por = admin.email

    # Se token estava em uso, bloqueia o usuário
    if token.usado_por:
        user_result = await db.execute(select(User).where(User.id == token.usado_por))
        user = user_result.scalar_one_or_none()
        if user:
            user.liberado = False
            user.trading_enabled = False

    db.add(AdminLog(
        admin_email=admin.email,
        action="revogar_token",
        target_user=token.usuario.email if token.usuario else None,
        detail=f"Token {token.codigo[:12]}... revogado"
    ))
    await db.commit()

    return {"status": "revogado", "token_id": token_id}


@router.get("/admin/licencas/resumo", tags=["Admin"])
async def resumo_licencas(
    admin: User = Depends(current_superuser),
    db: AsyncSession = Depends(get_async_session),
):
    """Resumo geral de licenças para o dashboard admin."""
    result = await db.execute(select(TokenLicenca))
    todos = result.scalars().all()

    total = len(todos)
    disponiveis = sum(1 for t in todos if t.disponivel)
    ativos = sum(1 for t in todos if t.status == "ativo")
    expirados = sum(1 for t in todos if t.expirado)
    revogados = sum(1 for t in todos if t.revogado)

    return {
        "total": total,
        "disponiveis": disponiveis,
        "ativos": ativos,
        "expirados": expirados,
        "revogados": revogados,
        "por_plano": {
            plano: sum(1 for t in todos if t.plano == plano)
            for plano in set(t.plano for t in todos)
        }
    }


# ===================== VERSÃO DO CLIENTE =====================

def _read_version() -> str:
    """Tenta ler a versão de várias localizações possíveis."""
    candidatos = [
        _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "..", "VERSION"),
        _os.path.join(_os.path.dirname(_os.path.abspath(_os.sys.argv[0])), "VERSION"),
        _os.path.join(_os.getcwd(), "VERSION"),
        _os.path.join(_os.path.dirname(_os.path.abspath(_os.sys.argv[0])), "..", "VERSION"),
    ]
    for p in candidatos:
        if _os.path.isfile(p):
            try:
                with open(p) as _f:
                    _v = _f.read().strip()
                    if _v:
                        return _v
            except Exception:
                pass
    return "1.0.0"


def _ver_gt(v1: str, v2: str) -> bool:
    """Compara versoes semanticas ex: '1.10.0' > '1.2.0'."""
    try:
        p1 = tuple(int(x) for x in v1.split("."))
        p2 = tuple(int(x) for x in v2.split("."))
        return p1 > p2
    except Exception:
        return v1 > v2


_CLIENT_VERSION = _read_version()


@router.get("/api/license/version", tags=["Licenciamento"])
async def client_version():
    """[PÚBLICO] Retorna a versão atual do cliente disponível."""
    return {
        "version": _CLIENT_VERSION,
        "download_url": "",
        "release_notes": "",
    }


@router.get("/api/check-update", tags=["Licenciamento"])
async def check_update():
    """Compara a versão local com a versão no servidor admin."""
    from src.core.config import settings

    info = {
        "current_version": _CLIENT_VERSION,
        "latest_version": _CLIENT_VERSION,
        "has_update": False,
        "download_url": "",
        "release_notes": "",
    }
    admin_url = (settings.ADMIN_SERVER_URL or "").rstrip("/")
    if not admin_url:
        return info
    try:
        async with _httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{admin_url}/api/license/version")
            if r.status_code == 200:
                data = r.json()
                info["latest_version"] = data.get("version", _CLIENT_VERSION)
                info["download_url"] = data.get("download_url", "")
                info["release_notes"] = data.get("release_notes", "")
                info["has_update"] = _ver_gt(info["latest_version"], _CLIENT_VERSION)
    except Exception:
        pass
    return info


@router.get("/minha-licenca", tags=["Usuário"])
async def minha_licenca(
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Retorna informações da licença do usuário logado."""
    result = await db.execute(
        select(TokenLicenca).where(TokenLicenca.usado_por == user.id)
    )
    token = result.scalar_one_or_none()

    return {
        "liberado": user.liberado,
        "trading_enabled": user.trading_enabled,
        "plano": user.plan.name if user.plan else None,
        "plano_expira_em": user.plan_expires_at.isoformat() if user.plan_expires_at else None,
        "expirado": bool(user.plan_expires_at and datetime.utcnow() > user.plan_expires_at),
        "client_version": _CLIENT_VERSION,
        "admin_server": settings.ADMIN_SERVER_URL or "",
        "token": {
            "codigo": token.codigo[:12] + "..." if token else None,
            "plano": token.plano if token else None,
            "criado_em": token.created_at.isoformat() if token else None,
            "ultima_atividade": token.ultima_atividade.isoformat() if token and token.ultima_atividade else None,
        } if token else None,
    }


# ===================== VALIDAÇÃO REMOTA (p/ clientes rodando local) =====================

@router.post("/api/license/validate", tags=["Licenciamento"])
async def validar_licenca_remota(
    body: LicencaValidateRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_session),
):
    """[PÚBLICO] Valida um token de licença enviado por uma instalação cliente.
    Chamado pela máquina do cliente ao ativar o token."""
    result = await db.execute(
        select(TokenLicenca).where(TokenLicenca.codigo == body.codigo.strip().upper())
    )
    token = result.scalar_one_or_none()

    if not token:
        return LicencaValidateResponse(valido=False, mensagem="Token inválido.")
    if token.revogado:
        return LicencaValidateResponse(valido=False, mensagem="Token revogado pelo administrador.")
    if token.usado_por:
        return LicencaValidateResponse(valido=False, mensagem="Token já utilizado.")
    if token.expirado:
        return LicencaValidateResponse(valido=False, mensagem="Token expirado.")
    if token.destinatario and body.cliente_email and token.destinatario != body.cliente_email.strip().lower():
        return LicencaValidateResponse(
            valido=False,
            mensagem=f"Token destinado a {token.destinatario}. Este email não corresponde.",
        )

    # Marca como usado (armazena email do cliente + IP)
    token.usado_em = datetime.utcnow()
    token.ultimo_ip = request.client.host if request.client else None
    if body.cliente_email:
        user_result = await db.execute(
            select(User).where(User.email == body.cliente_email.strip().lower())
        )
        found_user = user_result.scalar_one_or_none()
        if found_user:
            token.usado_por = found_user.id

    db.add(AdminLog(
        admin_email="sistema",
        action="ativar_token_remoto",
        target_user=token.destinatario or body.cliente_email,
        detail=f"Token {token.codigo[:12]}... ativado remotamente | Plano: {token.plano}"
    ))
    await db.commit()

    return LicencaValidateResponse(
        valido=True,
        plano=token.plano,
        expiracao_dias=token.expiracao_dias,
        mensagem="Token validado com sucesso.",
    )


# ===================== ATIVAÇÃO DO CLIENTE =====================

async def _ativar_token_local(token, user, db):
    """Ativa o usuario localmente com os dados do token."""
    user.liberado = True
    user.trading_enabled = True
    current_expiry = user.plan_expires_at or datetime.utcnow()
    new_expiry = datetime.utcnow() + timedelta(days=token.expiracao_dias)
    # So atualiza se o novo prazo for maior que o existente
    if new_expiry > current_expiry:
        user.plan_expires_at = new_expiry

    plan_result = await db.execute(select(Plan).where(Plan.name == token.plano))
    plan = plan_result.scalar_one_or_none()
    if plan:
        user.plan_id = plan.id

    db.add(AdminLog(
        admin_email="sistema",
        action="ativar_token",
        target_user=user.email,
        detail=f"Token {token.codigo[:12]}... | Plano: {token.plano}"
    ))


@router.post("/auth/ativar-token", tags=["Auth"])
async def ativar_token(
    body: AtivarTokenRequest,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Cliente ativa a conta com um token de licença.
    Se ADMIN_SERVER_URL estiver configurado (modo cliente remoto),
    valida o token no servidor admin."""
    # Modo cliente remoto: valida no servidor admin
    if settings.ADMIN_SERVER_URL:
        admin_url = settings.ADMIN_SERVER_URL.rstrip("/")
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(f"{admin_url}/api/license/validate", json={
                    "codigo": body.codigo.strip().upper(),
                    "cliente_email": user.email,
                })
                data = resp.json()
        except httpx.RequestError:
            raise HTTPException(status_code=503, detail="Não foi possível conectar ao servidor de licenças.")

        if not data.get("valido"):
            raise HTTPException(status_code=403, detail=data.get("mensagem", "Token inválido."))

        # Registra ativação localmente (token truncado + hash p/ evitar conflito)
        codigo_hash = hashlib.md5(body.codigo.strip().upper().encode()).hexdigest()[:16]
        token_local = TokenLicenca(
            codigo=f"REMOTE-{codigo_hash}-{user.id}",
            plano=data["plano"],
            expiracao_dias=data["expiracao_dias"],
            criado_por="remoto",
            usado_por=user.id,
            usado_em=datetime.utcnow(),
        )
        db.add(token_local)
        await _ativar_token_local(token_local, user, db)
        await db.commit()

        return {
            "status": "ativado",
            "plano": data["plano"],
            "expira_em": user.plan_expires_at.isoformat(),
        }

    # Modo local: valida no banco local (admin)
    result = await db.execute(
        select(TokenLicenca)
        .options(selectinload(TokenLicenca.usuario))
        .where(TokenLicenca.codigo == body.codigo.strip().upper())
    )
    token = result.scalar_one_or_none()

    if not token:
        raise HTTPException(status_code=404, detail="Token inválido.")
    if token.revogado:
        raise HTTPException(status_code=403, detail="Token revogado pelo administrador.")
    if token.usado_por:
        raise HTTPException(status_code=409, detail="Token já utilizado por outro usuário.")
    if token.expirado:
        raise HTTPException(status_code=403, detail="Token expirado.")
    if token.destinatario and token.destinatario != user.email.lower():
        raise HTTPException(
            status_code=403,
            detail=f"Token destinado a {token.destinatario}. Você não pode ativar este token.",
        )

    # Marca token como usado
    token.usado_por = user.id
    token.usado_em = datetime.utcnow()

    await _ativar_token_local(token, user, db)
    await db.commit()

    return {
        "status": "ativado",
        "plano": token.plano,
        "expira_em": user.plan_expires_at.isoformat(),
    }
