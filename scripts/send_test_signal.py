#!/usr/bin/env python3
"""
Envia uma mensagem de sinal de teste para um canal/grupo do Telegram,
no formato que src/telegram_copier.py::TelegramCopier.parse_signal reconhece.

Ferramenta auxiliar de teste manual -- NAO faz parte da aplicacao (nao
importa nada de src/). Existe pra testar o fluxo completo (recebimento no
Telegram -> parsing -> disparo de ordem -> resultado) sem depender de
esperar um sinal real chegar no canal de producao.

⚠️  SEGURANCA -- antes de usar:
  - Aponte SEMPRE para um canal/grupo de TESTE, nunca o canal real de sinais.
  - Use uma conta Telegram de teste (separada da sua conta pessoal/de producao),
    membro so do canal de teste -- evita ambiguidade na hora do copier
    resolver qual grupo e o alvo (TELEGRAM_GROUP_NAME/TELEGRAM_CHAT_ID do
    servidor casam pelo nome/ID entre os grupos da conta conectada).
  - O usuario RDE de teste que vai rodar o copier deve estar configurado
    com a corretora em modo DEMO -- "ganho ou perda" aqui nao deve envolver
    dinheiro real.

Credenciais (conta de teste, geradas em https://my.telegram.org):
    TG_TEST_API_ID    -- API ID da conta de teste
    TG_TEST_API_HASH  -- API Hash da conta de teste
    TG_TEST_PHONE     -- numero da conta de teste, com DDI (ex: +5511999999999)

Na primeira execucao, o Telethon pede o codigo de login (SMS/app) e cria um
arquivo de sessao local (default: tg_test_session.session, reaproveitado nas
proximas execucoes -- nao versionar esse arquivo).

Exemplos:
    # Sinal simples, dispara a ordem imediatamente ao ser parseado
    python scripts/send_test_signal.py --channel "RDE-TEST-SIGNALS" \\
        --direction CALL --symbol EURUSD-OTC --timeframe M1

    # Com horario de entrada (testa a espera ate perto do fechamento da vela)
    python scripts/send_test_signal.py --channel "RDE-TEST-SIGNALS" \\
        --direction PUT --symbol GBPUSD-OTC --timeframe M5 --entry-in 60

    # Pre-alerta -- deve ser IGNORADO pelo copier (nao dispara ordem)
    python scripts/send_test_signal.py --channel "RDE-TEST-SIGNALS" --pre-alert

    # Mensagem crua, formato livre
    python scripts/send_test_signal.py --channel "RDE-TEST-SIGNALS" \\
        --raw $'Sinal Confirmado\\nCALL EURUSD-OTC\\nM1\\nEntrada 14:30'

    # So mostra a mensagem que seria enviada, sem enviar de fato
    python scripts/send_test_signal.py --channel "RDE-TEST-SIGNALS" --dry-run
"""
import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta

try:
    from telethon import TelegramClient
except ImportError:
    print(
        "Dependencia ausente: pip install telethon (ou ative o venv do projeto, "
        "que ja tem telethon em requirements.txt).",
        file=sys.stderr,
    )
    sys.exit(1)


def build_message(direction: str, symbol: str, timeframe: str, entry_in_seconds: int | None, pre_alert: bool) -> str:
    """Monta o texto no formato que parse_signal() reconhece."""
    if pre_alert:
        return f"Aguarde confirmação\n{direction.upper()} {symbol.upper()}\n{timeframe.upper()}\nAnalisando..."

    lines = ["Sinal Confirmado", f"{direction.upper()} {symbol.upper()}", timeframe.upper()]
    if entry_in_seconds is not None:
        entry_time = (datetime.now() + timedelta(seconds=entry_in_seconds)).strftime("%H:%M")
        lines.append(f"Entrada {entry_time}")
    return "\n".join(lines)


async def resolve_channel(client: "TelegramClient", channel: str):
    """Resolve o canal por ID numerico, @username, ou nome (procurando entre
    os grupos/canais dos quais a conta ja e membro -- mesma logica de match
    por nome usada em TelegramCopier.start())."""
    if channel.lstrip("-").isdigit():
        return await client.get_entity(int(channel))
    if channel.startswith("@"):
        return await client.get_entity(channel)

    async for dialog in client.iter_dialogs():
        if channel.lower() in dialog.name.lower():
            return dialog.entity

    raise ValueError(
        f"Canal '{channel}' não encontrado entre os grupos desta conta. "
        "Confirme que a conta de teste é membro dele."
    )


async def send(api_id: int, api_hash: str, phone: str, session: str, channel: str, message: str):
    async with TelegramClient(session, api_id, api_hash) as client:
        await client.start(phone=phone)
        entity = await resolve_channel(client, channel)
        await client.send_message(entity, message)
        print(f"✅ Mensagem enviada para '{channel}':\n---\n{message}\n---")


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--channel", required=True, help="Nome, @username ou ID numérico do canal/grupo de TESTE")
    parser.add_argument("--raw", help="Mensagem crua completa (ignora --direction/--symbol/--timeframe/--entry-in)")
    parser.add_argument("--direction", default="CALL", choices=["CALL", "PUT"])
    parser.add_argument("--symbol", default="EURUSD-OTC")
    parser.add_argument("--timeframe", default="M1")
    parser.add_argument(
        "--entry-in", type=int, default=None, metavar="SEGUNDOS",
        help="Se definido, adiciona 'Entrada HH:MM' daqui a N segundos (testa a espera até o "
             "fechamento da vela). Sem isso, o sinal dispara a ordem assim que for parseado.",
    )
    parser.add_argument(
        "--pre-alert", action="store_true",
        help="Envia como pré-alerta/preparação -- deve ser IGNORADO pelo copier (testa o filtro de pré-sinal).",
    )
    parser.add_argument(
        "--session", default="tg_test_session",
        help="Caminho do arquivo de sessão Telethon da conta de teste (reaproveitado entre execuções).",
    )
    parser.add_argument("--dry-run", action="store_true", help="Só mostra a mensagem, não envia.")
    args = parser.parse_args()

    message = args.raw or build_message(args.direction, args.symbol, args.timeframe, args.entry_in, args.pre_alert)

    if args.dry_run:
        print(f"[dry-run] mensagem que seria enviada para '{args.channel}':\n---\n{message}\n---")
        return

    api_id = os.environ.get("TG_TEST_API_ID")
    api_hash = os.environ.get("TG_TEST_API_HASH")
    phone = os.environ.get("TG_TEST_PHONE")
    if not api_id or not api_hash or not phone:
        print(
            "Defina as variáveis de ambiente TG_TEST_API_ID, TG_TEST_API_HASH e TG_TEST_PHONE\n"
            "(conta de TESTE separada -- gere em https://my.telegram.org).\n"
            "Use --dry-run pra só conferir a mensagem sem precisar delas.",
            file=sys.stderr,
        )
        sys.exit(1)

    asyncio.run(send(int(api_id), api_hash, phone, args.session, args.channel, message))


if __name__ == "__main__":
    main()
