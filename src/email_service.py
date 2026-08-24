from src.core.config import settings
import logging

logger = logging.getLogger("rde")


def _get_mail():
    """Cria instância do FastMail apenas quando necessário."""
    if not settings.MAIL_PASSWORD:
        raise ValueError("MAIL_PASSWORD não configurada no .env")
    from fastapi_mail import FastMail, ConnectionConfig
    conf = ConnectionConfig(
        MAIL_USERNAME=settings.MAIL_USERNAME,
        MAIL_PASSWORD=settings.MAIL_PASSWORD,
        MAIL_FROM=settings.MAIL_FROM,
        MAIL_PORT=settings.MAIL_PORT,
        MAIL_SERVER=settings.MAIL_SERVER,
        MAIL_FROM_NAME=settings.MAIL_FROM_NAME,
        MAIL_STARTTLS=True,
        MAIL_SSL_TLS=False,
        USE_CREDENTIALS=True,
    )
    return FastMail(conf)


async def send_password_reset_email(email: str, token: str):
    from fastapi_mail import MessageSchema
    reset_url = f"{settings.FRONTEND_URL}/reset-password?token={token}"
    message = MessageSchema(
        subject="RDE - Recuperação de Senha",
        recipients=[email],
        body=f"""
        <html>
          <body style="font-family:sans-serif;background:#0F172A;color:#F8FAFC;padding:40px;">
            <div style="max-width:600px;margin:0 auto;background:#1E293B;padding:30px;border-radius:20px;border:1px solid #334155;">
              <h1 style="color:#3B82F6;">RDE</h1>
              <h2 style="color:#F8FAFC;">Recuperação de Senha</h2>
              <p style="color:#94A3B8;font-size:16px;line-height:1.6;">
                Clique no botão abaixo para redefinir sua senha:
              </p>
              <div style="text-align:center;margin:40px 0;">
                <a href="{reset_url}"
                   style="background:#3B82F6;color:#fff;padding:16px 32px;border-radius:12px;text-decoration:none;font-weight:800;font-size:14px;">
                  Redefinir Senha →
                </a>
              </div>
              <p style="color:#64748B;font-size:12px;">
                Se não solicitou, ignore este email. Link expira em 1 hora.
              </p>
            </div>
          </body>
        </html>
        """,
        subtype="html",
    )
    try:
        fm = _get_mail()
        await fm.send_message(message)
        logger.info(f"Email de recuperação enviado para {email}")
    except ValueError as e:
        logger.warning(f"Email não enviado: {e}")
        raise
    except Exception as e:
        logger.error(f"Erro ao enviar email: {e}")
        raise


async def send_plan_upgrade_email(email: str, plan_name: str):
    from fastapi_mail import MessageSchema
    message = MessageSchema(
        subject="RDE - Seu plano foi atualizado!",
        recipients=[email],
        body=f"""
        <html>
          <body style="font-family:sans-serif;background:#0F172A;color:#F8FAFC;padding:40px;">
            <h1 style="color:#22C55E;">RDE</h1>
            <h2>Seu plano agora é <strong style="color:#22C55E">{plan_name}</strong></h2>
            <p>Obrigado pela confiança. Seu plano está ativo.</p>
          </body>
        </html>
        """,
        subtype="html",
    )
    try:
        fm = _get_mail()
        await fm.send_message(message)
    except Exception as e:
        logger.warning(f"Email de upgrade não enviado: {e}")


async def send_plan_expiry_email(email: str, plan_name: str):
    from fastapi_mail import MessageSchema
    message = MessageSchema(
        subject="RDE - Seu plano expirou",
        recipients=[email],
        body=f"""
        <html>
          <body style="font-family:sans-serif;background:#0F172A;color:#F8FAFC;padding:40px;">
            <h1 style="color:#22C55E;">RDE</h1>
            <h2>Seu plano <strong>{plan_name}</strong> expirou.</h2>
            <p>Renove para continuar operando.</p>
          </body>
        </html>
        """,
        subtype="html",
    )
    try:
        fm = _get_mail()
        await fm.send_message(message)
    except Exception as e:
        logger.warning(f"Email de expiração não enviado: {e}")
