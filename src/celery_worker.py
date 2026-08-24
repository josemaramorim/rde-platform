import logging
from celery import Celery
from src.core.config import settings
from src.database.session import SessionLocal
from src.executor import execute_trade
from src.models.user import User

logger = logging.getLogger("rde-tasks")

# Inicialização do Celery utilizando as configurações do sistema
celery = Celery(
    "rde_tasks",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

# Configurações básicas de serialização e fuso horário
celery.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)

# 🛠️ CORREÇÃO CRÍTICA: Força o Celery a usar o protocolo RESP2 (compatível com o Redis do Windows)
# Isso elimina o erro de comando 'HELLO' desconhecido
celery.conf.redis_backend_transport_options = {'global_keyprefix': 'celery_'}
celery.conf.broker_transport_options = {"redis_version": "6.0.0"}


@celery.task(bind=True, max_retries=2, default_retry_delay=5)
def process_signal(self, email: str, signal: str):
    """
    Background task: look up user and execute trade.
    Retries up to 2 times on transient failures.
    """
    logger.info(f"📥 Sinal recebido para o usuário {email}: {signal}")
    db = SessionLocal()
    
    try:
        # Busca o usuário na sessão síncrona dedicada da Task
        user = db.query(User).filter(User.email == email).first()

        if not user:
            logger.warning(f"❌ Usuário não encontrado: {email}")
            return {"error": "user not found"}
            
        if not user.is_active:
            logger.warning(f"🚫 Usuário inativo no sistema: {email}")
            return {"error": "inactive user"}

        # Executa a operação na corretora configurada (IQ, Quotex, etc.)
        logger.info(f"🚀 Enviando ordem para o executor do usuário (ID: {user.id})...")
        result = execute_trade(user, signal, db)
        
        # Garante a persistência de logs locais ou alterações feitas pelo executor
        db.commit()
        logger.info(f"✅ Processamento do sinal concluído com sucesso para {email}.")
        return {"success": True, "result": result}

    except Exception as exc:
        db.rollback()
        logger.error(f"🚨 Erro ao processar sinal para {email}: {str(exc)}. Tentando novamente...")
        # Recomeça a task em caso de erro temporário (ex: instabilidade no SQLite ou Redis)
        raise self.retry(exc=exc)

    finally:
        db.close()