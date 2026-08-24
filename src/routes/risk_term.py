from __future__ import annotations
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, EmailStr
from src.database.session import get_async_session
from src.auth.users import current_active_user
from src.models.user import User
from src.models.risk_term import RiskTermAcceptance

router = APIRouter(prefix="/risk-term", tags=["Risk Term"])

TERM_VERSION = "1.0"

TERM_TEXT = """TERMO DE RESPONSABILIDADE E ASSUNÇÃO DE RISCO — RDE PLATFORM

Versão 1.0 — Atualizado em Julho de 2026

1. OBJETO
O presente Termo de Responsabilidade e Assunção de Risco ("Termo") estabelece os termos e condições sob os quais o(a) USUÁRIO(A) utilizará a plataforma RDE Platform ("Plataforma"), incluindo, mas não se limitando a, cópia automatizada de sinais de trading, gerenciamento de capital e operações em corretoras de opções binárias.

2. DECLARAÇÃO DE RISCO
O(A) USUÁRIO(A) declara ter pleno conhecimento e compreensão de que:
a) Operações em opções binárias envolvem risco significativo de perda financeira;
b) O mercado financeiro é volátil e imprevisível;
c) Não existe garantia de lucro ou retorno do capital investido;
d) Resultados passados não garantem resultados futuros;
e) A cópia automatizada de sinais não elimina os riscos inerentes ao trading;
f) O(A) USUÁRIO(A) pode perder total ou parcialmente o capital investido.

3. RESPONSABILIDADE
O(A) USUÁRIO(A) é o(a) único(a) e exclusivo(a) responsável por:
a) Todas as decisões de investimento tomadas através da Plataforma;
b) A escolha de corretora, ativos e valores investidos;
c) As perdas financeiras decorrentes das operações realizadas;
d) O cumprimento de todas as leis e regulamentações aplicáveis em sua jurisdição.

4. ISENTAÇÃO DE RESPONSABILIDADE
A RDE Platform, seus desenvolvedores, administradores e afiliados são isentos de qualquer responsabilidade por:
a) Perdas financeiras sofridas pelo(a) USUÁRIO(A);
b) Danos diretos, indiretos, incidentais ou consequenciais;
c) Interrupções de serviço, falhas técnicas ou erros de sistema;
d) Ações de terceiros, incluindo corretoras e provedores de sinais;
e) Decisões de trading tomadas com base nos sinais fornecidos.

5. GARANTIA LIMITADA
A Plataforma é fornecida "COMO ESTÁ" e "CONFORME DISPONÍVEL", sem garantias de qualquer tipo, expressas ou implícitas, incluindo, mas não se limitando a, garantias de merchantability, adequação a um fim específico ou não violação.

6. DADOS PESSOAIS
O(A) USUÁRIO(A) autoriza o tratamento de seus dados pessoais conforme a Política de Privacidade da Plataforma, exclusivamente para fins de operacionalização do serviço.

7. VIGÊNCIA
Este Termo entra em vigor na data de aceitação pelo(a) USUÁRIO(A) e permanecerá válido enquanto a Plataforma estiver em operação.

8. ACEITAÇÃO
Ao clicar em "Aceito o Termo de Risco" e inserir seus dados, o(a) USUÁRIO(A) declara que leu, compreendeu e aceita integralmente todos os termos e condições deste Termo de Responsabilidade e Assunção de Risco."""


class AcceptTermRequest(BaseModel):
    full_name: str
    email: EmailStr
    cpf_or_id: str
    accepted: bool


@router.get("/status")
async def get_term_status(
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    result = await db.execute(
        select(RiskTermAcceptance).where(RiskTermAcceptance.user_id == user.id)
    )
    record = result.scalar_one_or_none()
    if not record:
        return {"accepted": False, "exists": False, "term_version": TERM_VERSION}
    return {
        "accepted": record.accepted,
        "exists": True,
        "term_version": record.term_version,
        "accepted_at": record.accepted_at.isoformat() if record.accepted_at else None,
    }


@router.get("/text")
async def get_term_text():
    return {"text": TERM_TEXT, "version": TERM_VERSION}


@router.post("/accept")
async def accept_term(
    req: AcceptTermRequest,
    request: Request,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    result = await db.execute(
        select(RiskTermAcceptance).where(RiskTermAcceptance.user_id == user.id)
    )
    existing = result.scalar_one_or_none()

    ip = request.client.host if request.client else ""
    ua = request.headers.get("user-agent", "")

    if existing:
        existing.accepted = req.accepted
        existing.email_confirmed = req.email
        existing.full_name = req.full_name
        existing.cpf_or_id = req.cpf_or_id
        existing.ip_address = ip
        existing.user_agent = ua
        existing.term_version = TERM_VERSION
        existing.accepted_at = datetime.utcnow()
        existing.declined_at = None if req.accepted else datetime.utcnow()
        db.add(existing)
    else:
        record = RiskTermAcceptance(
            user_id=user.id,
            accepted=req.accepted,
            email_confirmed=req.email,
            full_name=req.full_name,
            cpf_or_id=req.cpf_or_id,
            ip_address=ip,
            user_agent=ua,
            term_version=TERM_VERSION,
            accepted_at=datetime.utcnow(),
            declined_at=None if req.accepted else datetime.utcnow(),
        )
        db.add(record)

    await db.commit()
    return {"status": "ok", "accepted": req.accepted}
