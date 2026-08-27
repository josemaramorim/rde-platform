"""
Telegram Copier — RDE AI Manager
Listens to Telegram signal groups and executes trades automatically.

Supports 2 brokers:
  - Deriv (API Token)
  - IQ Option (Email + Password)

Uses the BrokerSetting table to determine which broker and credentials to use.
"""
import os
import sys
import asyncio
import logging
import re
import json
import random
from datetime import datetime, timedelta
from telethon import TelegramClient, events
from dotenv import load_dotenv
import aiohttp

# Força UTF-8 no output para Windows (evita crash com emojis)
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

# Broker adapters
from src.broker.deriv import DerivBroker
from src.broker.iqoption import IQOptionBroker
from src.core.config import settings

# Carrega variáveis do arquivo .env
load_dotenv()

# Configuração de Logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', stream=sys.stdout, force=True)
logger = logging.getLogger("RDE-AI-Manager")

# Default symbol per broker
DEFAULT_SYMBOL = {
    "deriv": "R_100",
    "iqoption": "EURUSD-OTC",
}


class TelegramCopier:
    def __init__(self, session_name='rde_user_session', user_id=None, broker_name=None):
        self.api_id = settings.TELEGRAM_API_ID or 24906269
        self.api_hash = settings.TELEGRAM_API_HASH or "4826f9dd0be48b617f94fc04b88ffabc"
        chats_list = []
        if settings.TELEGRAM_CHAT_ID:
            for c in settings.TELEGRAM_CHAT_ID.split(","):
                c = c.strip()
                if c and c.lstrip('-').isdigit():
                    chats_list.append(int(c))
                elif c and c.startswith("@"):
                    chats_list.append(c)

        self.target_chats = chats_list if chats_list else None

        # User context (passed from API)
        self._user_id = user_id
        self._broker_name_hint = broker_name

        # Broker config (loaded from DB on connect)
        self.broker_name = broker_name or "deriv"
        self.is_demo_account = True
        self.base_stake = 1.0
        self.current_stake = self.base_stake
        
        # Gerenciamento — 3 sessoes de 1% com 3 entradas cada
        self.session_manager = None  # Inicializado apos conectar broker
        self.stop_loss_pct = 0.20

        # Meta Lock (auto-trava ao bater meta)
        self.auto_lock_meta = False
        self.meta_hit_today = False
        self.meta_hit_date = None
        
        # Stats do Dia
        self.signals_count = 0
        self.success_count = 0
        
        # Status da Sessão
        self.initial_balance = 0.0
        self.current_balance = 0.0
        uid = user_id or "shared"
        self.status_file = f"live_status_{uid}.json"
        self.ops_file = f"live_operations_{uid}.json"
        self.state_file = f"{session_name}_stats.json"

        # Evita ordens consecutivas enquanto uma vela esta aberta
        self._order_in_progress = False
        self._balance_before_trade = 0.0

        # Lock para evitar reconexoes concorrentes (heartbeat + reconnect_loop)
        self._reconnect_lock = asyncio.Lock()
        self._heartbeat_interval = 30  # segundos entre pings de saude
        
        self.session_name = session_name
        self.client = self._create_telegram_client()
        self.broker = None
        self.is_running = False

    def _create_telegram_client(self):
        """Cria cliente Telegram. Usa sessao fixa se disponivel, ou temporaria."""
        import os, time
        base = "rde_user_session"
        if self._user_id:
            base = f"rde_user_session_{self._user_id}"
        # Tenta com sessao fixa primeiro
        try:
            return TelegramClient(
                base, self.api_id, self.api_hash,
                connection_retries=None,
                retry_delay=2,
                auto_reconnect=True,
                request_retries=10,
                timeout=30,
            )
        except Exception:
            logger.warning("Usando sessao temporaria (sessao fixa indisponivel).")
            self.session_name = f"rde_session_{int(time.time())}"
            return TelegramClient(
                self.session_name, self.api_id, self.api_hash,
                connection_retries=None,
                retry_delay=2,
                auto_reconnect=True,
                request_retries=10,
                timeout=30,
            )

    def load_state(self):
        """Carrega estatísticas persistentes do dia."""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as f:
                    data = json.load(f)
                    if data.get('date') == datetime.now().strftime("%Y-%m-%d"):
                        self.signals_count = data.get('signals_today', 0)
                        self.success_count = data.get('success_count', 0)
                        logger.info(f"[CHART] Estatísticas carregadas: {self.signals_count} sinais, {self.success_count} wins.")
            except: pass

    def _load_operations(self) -> list:
        if os.path.exists(self.ops_file):
            try:
                with open(self.ops_file, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def _write_operations(self, ops: list):
        today = datetime.now().strftime("%Y-%m-%d")
        ops = [o for o in ops if o.get("date") == today][-50:]
        try:
            with open(self.ops_file, "w") as f:
                json.dump(ops, f)
        except Exception:
            pass

    def _save_pending_operation(self, symbol: str, direction: str, stake: float, op_id: str):
        """Salva operacao PENDENTE no live_operations.json ao enviar ordem."""
        ops = self._load_operations()
        ops.append({
            "id": op_id,
            "symbol": symbol,
            "direction": direction,
            "result": "PENDENTE",
            "profit": 0,
            "stake": stake,
            "time": datetime.now().strftime("%H:%M:%S"),
            "date": datetime.now().strftime("%Y-%m-%d"),
        })
        self._write_operations(ops)

    def _resolve_operation(self, op_id: str, status: str, stake: float, profit: float):
        """Atualiza operacao PENDENTE para WIN/LOSS no live_operations.json."""
        ops = self._load_operations()
        for op in ops:
            if op.get("id") == op_id:
                op["result"] = "WIN" if status == "won" else "LOSS"
                op["profit"] = round(profit, 2)
                break
        self._write_operations(ops)

    def save_state(self):
        """Salva estatísticas atuais para não perder no restart."""
        data = {
            'date': datetime.now().strftime("%Y-%m-%d"),
            'signals_today': self.signals_count,
            'success_count': self.success_count
        }
        try:
            with open(self.state_file, 'w') as f:
                json.dump(data, f)
        except: pass

    def update_live_status(self, last_msg="Aguardando sinais..."):
        """Atualiza o arquivo JSON para o Dashboard mostrar em tempo real."""
        profit = self.current_balance - self.initial_balance
        
        # Info do SessionManager
        sm = {}
        if self.session_manager:
            sm = self.session_manager.get_status()
        
        status = {
            "broker": self.broker_name,
            "account_mode": "Demo" if self.is_demo_account else "Real",
            "initial_balance": round(self.initial_balance, 2),
            "current_balance": round(self.current_balance, 2),
            "profit": round(profit, 2),
            "profit_pct": round((profit / self.initial_balance * 100), 2) if self.initial_balance > 0 else 0,
            "daily_target": sm.get("daily_target", round(self.initial_balance * 0.03, 2)),
            "daily_profit": sm.get("daily_profit", 0.0),
            "daily_progress_pct": sm.get("daily_progress_pct", 0),
            "current_session": sm.get("current_session", 1),
            "session_entries_used": sm.get("session_entries_used", 0),
            "session_profit": sm.get("session_profit", 0.0),
            "session_target": sm.get("session_target", 0.0),
            "management_pct": 3.0,
            "current_stake": sm.get("stake", 0.0),
            "stake_pct": 1.0,
            "signals_today": self.signals_count,
            "success_count": self.success_count,
            "success_rate": round((self.success_count / self.signals_count * 100), 1) if self.signals_count > 0 else 0,
            "total_trades": sm.get("total_trades", 0),
            "wins": sm.get("wins", 0),
            "losses": sm.get("losses", 0),
            "win_rate": sm.get("win_rate", 0),
            "gale_level": sm.get("gale_level", 0),
            "last_message": last_msg,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "meta_hit_today": self.meta_hit_today,
            "auto_lock_meta": self.auto_lock_meta,
            "meta_hit_date": self.meta_hit_date,
            "blocked": getattr(self, '_blocked', False),
            "source": "telegram"
        }
        with open(self.status_file, 'w') as f:
            json.dump(status, f)

    def _load_risk_config(self):
        """Carrega configuracoes de risco do banco de dados (por broker ativo)."""
        try:
            from src.database.session import SessionLocal
            from src.models.user import User
            from src.models.broker import BrokerSetting
            from src.services.management_3pct import SessionManager
            db = SessionLocal()
            q = db.query(User)
            if self._user_id:
                user = q.filter(User.id == self._user_id).first()
            else:
                user = q.filter_by(email=settings.ADMIN_EMAIL).first()
            if user:
                setting = db.query(BrokerSetting).filter_by(
                    user_id=user.id, is_active=True
                ).first()
                if setting:
                    self.base_stake = setting.stake or 1.0
                    self.current_stake = self.base_stake
                    self.stop_loss_pct = (setting.stop_loss_pct or 20.0) / 100
                    self.auto_lock_meta = setting.auto_lock_meta or False
                    self.meta_hit_today = setting.meta_hit_today or False
                    self.meta_hit_date = setting.meta_hit_date
                    logger.info(
                        f"Risco carregado do broker {setting.broker_name}: "
                        f"stake={self.base_stake} stop={self.stop_loss_pct*100}%"
                    )
                else:
                    if user.stake:
                        self.base_stake = user.stake
                        self.current_stake = user.stake
                    self.auto_lock_meta = user.auto_lock_meta or False
                    self.meta_hit_today = user.meta_hit_today or False
                    self.meta_hit_date = user.meta_hit_date
            db.close()
        except Exception as e:
            logger.warning(f"Usando config padrao de risco: {e}")

    def _check_risk_term(self) -> bool:
        """Verifica se o cliente aceitou o Termo de Risco."""
        try:
            from src.database.session import SessionLocal
            from src.models.user import User
            from src.models.risk_term import RiskTermAcceptance
            db = SessionLocal()
            q = db.query(User)
            if self._user_id:
                user = q.filter(User.id == self._user_id).first()
            else:
                user = q.filter_by(email=settings.ADMIN_EMAIL).first()
            if not user:
                db.close()
                return False
            record = db.query(RiskTermAcceptance).filter_by(
                user_id=user.id, accepted=True
            ).first()
            db.close()
            return record is not None
        except Exception as e:
            logger.warning(f"Erro ao verificar termo de risco: {e}")
            return False

    def _check_meta_lock(self) -> bool:
        """Retorna True se a meta ja foi batida hoje e o auto-lock esta ativo."""
        if not self.auto_lock_meta:
            return False
        today = datetime.now().strftime("%Y-%m-%d")
        # Se a meta foi batida em dia anterior, reseta automaticamente
        if self.meta_hit_today and self.meta_hit_date and self.meta_hit_date != today:
            logger.info(f"Novo dia detectado ({today}). Resetando meta do dia anterior.")
            self.meta_hit_today = False
            self.meta_hit_date = None
            self._reset_meta_in_db()
            return False
        if not self.meta_hit_today:
            return False
        if self.meta_hit_date == today:
            logger.info(f"META JA BATIDA HOJE ({today}). Copier bloqueado ate 00:01.")
            self.update_live_status(f"META JA BATIDA HOJE! Bloqueado ate 00:01.")
            return True
        return False

    def _reset_meta_in_db(self):
        """Reseta flags de meta no banco de dados para o novo dia."""
        try:
            from src.database.session import SessionLocal
            from src.models.user import User
            from src.models.broker import BrokerSetting
            db = SessionLocal()
            q = db.query(User)
            if self._user_id:
                user = q.filter(User.id == self._user_id).first()
            else:
                user = q.filter_by(email=settings.ADMIN_EMAIL).first()
            if user:
                setting = db.query(BrokerSetting).filter_by(
                    user_id=user.id, is_active=True
                ).first()
                if setting:
                    setting.meta_hit_today = False
                    setting.meta_hit_date = None
                    setting.today_trades = 0
                    setting.today_profit = 0.0
                    db.commit()
                else:
                    user.meta_hit_today = False
                    user.meta_hit_date = None
                    db.commit()
            db.close()
        except Exception as e:
            logger.warning(f"Erro ao resetar meta no DB: {e}")

    def _save_meta_hit(self):
        """Persiste no banco que a meta foi batida hoje (por broker ativo)."""
        if not self.auto_lock_meta:
            return
        try:
            from src.database.session import SessionLocal
            from src.models.user import User
            from src.models.broker import BrokerSetting
            db = SessionLocal()
            q = db.query(User)
            if self._user_id:
                user = q.filter(User.id == self._user_id).first()
            else:
                user = q.filter_by(email=settings.ADMIN_EMAIL).first()
            if user:
                # Save meta_hit to the active broker setting
                setting = db.query(BrokerSetting).filter_by(
                    user_id=user.id, is_active=True
                ).first()
                if setting:
                    setting.meta_hit_today = True
                    setting.meta_hit_date = datetime.now().strftime("%Y-%m-%d")
                    db.commit()
                    logger.info(
                        f"Meta hit salvo no broker {setting.broker_name}."
                    )
                else:
                    # Fallback to user-level
                    user.meta_hit_today = True
                    user.meta_hit_date = datetime.now().strftime("%Y-%m-%d")
                    db.commit()
                    logger.info("Meta hit salvo no usuario (fallback).")

                # ── Auto-mark planilha ────────────────────────────────
                self._auto_mark_planilha(user, db)
                
                # ── Avança para o próximo dia após a meta ser batida ────────────────────────────────
                self._advance_to_next_day(user, db)
            db.close()
        except Exception as e:
            logger.warning(f"Erro ao salvar meta hit: {e}")

    def _auto_mark_planilha(self, user, db):
        """Marca dia na planilha automaticamente ao bater meta."""
        try:
            from src.models.planilha import PlanilhaProgress
            from sqlalchemy import select as sa_select, and_

            sm = self.session_manager
            if not sm:
                return

            # Calcula dia atual: dias ja completados + 1
            result = db.execute(
                sa_select(PlanilhaProgress).where(
                    PlanilhaProgress.user_id == user.id,
                    PlanilhaProgress.completed == True,
                )
            )
            completed_days = len(result.scalars().all())
            current_day = completed_days + 1

            # Verifica se ja marcou este dia
            existing = db.execute(
                sa_select(PlanilhaProgress).where(
                    and_(
                        PlanilhaProgress.user_id == user.id,
                        PlanilhaProgress.day_number == current_day,
                    )
                )
            ).scalar_one_or_none()

            if existing and existing.completed:
                return

            if existing:
                existing.completed = True
                existing.capital_base = sm.initial_balance
                existing.daily_profit = sm.daily_profit
                existing.completed_at = datetime.utcnow()
                db.add(existing)
            else:
                record = PlanilhaProgress(
                    user_id=user.id,
                    day_number=current_day,
                    completed=True,
                    capital_base=sm.initial_balance,
                    daily_profit=sm.daily_profit,
                    completed_at=datetime.utcnow(),
                )
                db.add(record)

            db.commit()
            logger.info(f"[PLANILHA] Dia {current_day} marcado automaticamente! Profit: ${sm.daily_profit:.2f}")
        except Exception as e:
            logger.warning(f"Erro ao marcar planilha: {e}")

    async def _advance_to_next_day(self, user, db):
        """
        Avança para o próximo dia na planilha quando uma meta é batida.
        Isso será acionado de forma automática toda vez que uma meta é batida.
        Atualiza o balance com um acréscimo de 3% para o próximo dia.
        Reseta flags de meta_hit_today no banco para que o próximo dia possa atingir sua meta.
        """
        try:
            from src.models.planilha import PlanilhaProgress
            from sqlalchemy import select as sa_select, and_
            from src.services.management_3pct import Management3Pct
            from src.models.user import User
            from src.models.broker import BrokerSetting

            sm = self.session_manager
            if not sm:
                return

            # Calcula o número do próximo dia: dias ja completados + 1
            result = db.execute(
                sa_select(PlanilhaProgress).where(
                    PlanilhaProgress.user_id == user.id,
                    PlanilhaProgress.completed == True,
                )
            )
            completed_days = len(result.scalars().all())
            next_day = completed_days + 1

            # Verifica se o próximo dia já está marcado
            existing = db.execute(
                sa_select(PlanilhaProgress).where(
                    and_(
                        PlanilhaProgress.user_id == user.id,
                        PlanilhaProgress.day_number == next_day,
                    )
                )
            ).scalar_one_or_none()

            if existing and existing.completed:
                return  # Já marcado, não é necessário avançar

            # Calcula o novo balance para o próximo dia (3% a mais)
            mgmt = Management3Pct()
            next_balance = round(sm.current_balance * 1.03, 2)  # Aumento de 3%

            if existing:
                existing.completed = True
                existing.capital_base = next_balance
                existing.daily_profit = 0.0  # Novo dia, lucro zerado
                existing.completed_at = datetime.utcnow()
                db.add(existing)
            else:
                record = PlanilhaProgress(
                    user_id=user.id,
                    day_number=next_day,
                    completed=True,
                    capital_base=next_balance,
                    daily_profit=0.0,
                    completed_at=datetime.utcnow(),
                )
                db.add(record)

            # ── Reseta flags de meta no banco para o próximo dia ────────────────────────────────
            today_str = datetime.now().strftime("%Y-%m-%d")
            
            # Atualiza o broker setting ativo
            setting = db.query(BrokerSetting).filter_by(
                user_id=user.id, is_active=True
            ).first()
            if setting:
                setting.meta_hit_today = False
                setting.meta_hit_date = None
                logger.info(f"Meta hit resetado para o broker {setting.broker_name}.")
            else:
                # Fallback para user-level
                user_obj = db.query(User).filter_by(email=user.email).first()
                if user_obj:
                    user_obj.meta_hit_today = False
                    user_obj.meta_hit_date = None
                    logger.info("Meta hit resetado no usuario (fallback).")
            
            db.commit()
            
            # Atualiza o session_manager com o novo balance e reset
            self.initial_balance = next_balance
            self.current_balance = next_balance
            if self.session_manager:
                self.session_manager.new_day(next_balance)
            
            # Reseta flags locais
            self.meta_hit_today = False
            self.meta_hit_date = None
            
            logger.info(f"[PLANILHA] Próximo dia {next_day} avançado automaticamente! Novo capital base: ${next_balance:.2f}")
            
            # Atualiza o status ao vivo
            self.update_live_status(f"Meta batida! Avançando para o dia {next_day} (novo capital base: ${next_balance:.2f})")
            
        except Exception as e:
            logger.warning(f"Erro ao avançar para o próximo dia: {e}")

    def _load_broker_from_db(self):
        """
        Read broker settings from the database.
        Returns: (broker_name, credentials_dict, is_demo)
        is_demo is forced from the user's plan.
        """
        try:
            from src.database.session import SessionLocal
            from src.models.user import User, Plan
            from src.models.broker import BrokerSetting
            from src.core.security import encryption_service

            db = SessionLocal()
            q = db.query(User)
            if self._user_id:
                user = q.filter(User.id == self._user_id).first()
            else:
                user = q.filter_by(email=settings.ADMIN_EMAIL).first()
            if not user:
                logger.error("[CROSS] Usuario nao encontrado no DB.")
                db.close()
                return None, None, True

            # If a specific broker was requested, prefer it
            setting = None
            if self._broker_name_hint:
                setting = (
                    db.query(BrokerSetting)
                    .filter_by(user_id=user.id, broker_name=self._broker_name_hint, is_active=True)
                    .first()
                )

            # Fallback to any active broker
            if not setting:
                setting = (
                    db.query(BrokerSetting)
                    .filter_by(user_id=user.id, is_active=True)
                    .first()
                )

            # Use per-broker is_demo; fall back to plan-level default
            if setting:
                is_demo = bool(setting.is_demo)
            elif user.plan:
                is_demo = bool(user.plan.is_demo)
            else:
                is_demo = True

            if setting:
                broker_name = setting.broker_name.lower()

                # Decrypt credentials
                def _decrypt(val):
                    if not val:
                        return None
                    try:
                        dec = encryption_service.decrypt(val)
                        return dec if dec != "ERROR_DECRYPT" else val
                    except:
                        return val

                dec_token = _decrypt(setting.api_token) or ""
                email = setting.iq_email
                password = _decrypt(setting.iq_password)

                if "|||" in dec_token:
                    t_email, t_pass = dec_token.split("|||", 1)
                    if not email:
                        email = t_email
                    if not password:
                        password = t_pass

                creds = {
                    "api_token": dec_token,
                    "email": email or (user.iq_email if user else None),
                    "password": password or (_decrypt(user.iq_password) if user and user.iq_password else None),
                }
                # Enriquecer com campos específicos do broker
                try:
                    extra = setting.get_credentials()
                    for k, v in extra.items():
                        if k not in creds or creds[k] is None:
                            creds[k] = v
                except Exception:
                    pass

                db.close()
                return broker_name, creds, is_demo
            else:
                # Fallback to user model fields
                broker_name = (user.broker or "deriv").lower()
                creds = {
                    "api_token": user.api_token,
                    "email": user.iq_email,
                }
                db.close()
                return broker_name, creds, is_demo

        except Exception as e:
            logger.error(f"[CROSS] Erro ao ler DB: {e}")
            return None, None, True

    async def connect_broker(self):
        """Connect to the appropriate broker based on DB settings."""
        try:
            if self.broker is not None:
                try:
                    self.broker.disconnect()
                except Exception:
                    pass
                self.broker = None
                await asyncio.sleep(2)

            broker_name, creds, is_demo = self._load_broker_from_db()
            
            if not broker_name or not creds:
                # Fallback to .env Deriv token
                logger.warning("[WARN] Sem config no DB. Usando .env como fallback.")
                broker_name = "deriv"
                creds = {"api_token": os.getenv("DERIV_API_TOKEN", "")}
                is_demo = True
            
            # ── Verificar Termo de Risco ──────────────────────────────
            if not self._check_risk_term():
                logger.error("[RISCO] Cliente NAO aceitou o Termo de Risco. Copier BLOQUEADO.")
                self.update_live_status("BLOQUEADO: Aceite o Termo de Risco na plataforma.")
                return False
            
            self.broker_name = broker_name
            self.is_demo_account = is_demo
            
            logger.info(f"[CONFIG] Broker: {broker_name.upper()} | Modo: {'DEMO' if is_demo else 'REAL'}")
            
            # ── Deriv ──────────────────────────────────────────────────
            if broker_name in ("deriv", "deriv_demo", "deriv_real"):
                from src.broker.deriv import DerivBroker
                token = creds.get("api_token") or os.getenv("DERIV_API_TOKEN", "")
                if not token:
                    logger.error("Nenhum token Deriv encontrado.")
                    return False
                self.broker = DerivBroker(api_token=token, is_demo=is_demo, app_id=creds.get("app_id") or "16929")
                self.broker.connect()
            
            # ── IQ Option ──────────────────────────────────────────────
            elif broker_name == "iqoption":
                from src.broker.iqoption import IQOptionBroker
                api_token = creds.get("api_token") or ""
                email = creds.get("email") or os.getenv("IQ_EMAIL", "")
                password = creds.get("password") or ""
                if "|||" in api_token:
                    email, password = api_token.split("|||", 1)
                if not email or not password:
                    logger.error("[CROSS] Credenciais IQ Option ausentes.")
                    return False
                self.broker = IQOptionBroker(
                    email=email, password=password, is_demo=is_demo
                )
                self.broker.connect()

            # ── Quotex ─────────────────────────────────────────────────
            elif broker_name == "quotex":
                from src.broker.quotex import QuotexBroker
                api_token = creds.get("api_token") or ""
                email = creds.get("email") or os.getenv("QUOTEX_EMAIL", "")
                password = creds.get("password") or ""
                if "|||" in api_token:
                    email, password = api_token.split("|||", 1)
                if not email or not password:
                    logger.error("[CROSS] Credenciais Quotex ausentes.")
                    return False
                self.broker = QuotexBroker(
                    email=email, password=password, is_demo=is_demo
                )
                self.broker.connect()

            # ── Pocket Option ──────────────────────────────────────────
            elif broker_name == "pocketoption":
                from src.broker.pocketoption import PocketOptionBroker
                ssid = creds.get("api_token") or creds.get("ssid") or os.getenv("POCKET_SSID", "")
                if not ssid:
                    logger.error("[CROSS] SSID Pocket Option ausente.")
                    return False
                self.broker = PocketOptionBroker(
                    ssid=ssid, is_demo=is_demo
                )
                self.broker.connect()
            
            else:
                logger.error(f"[CROSS] Broker não suportado: {broker_name}")
                return False
            
            # Get initial balance
            try:
                if hasattr(self.broker, "async_get_balance"):
                    self.initial_balance = await self.broker.async_get_balance()
                else:
                    self.initial_balance = self.broker.get_balance()
            except Exception as e:
                logger.warning(f"Erro ao ler saldo inicial do broker: {e}")
                self.initial_balance = 0.0

            if self.initial_balance is None:
                self.initial_balance = 0.0
            
            self.current_balance = self.initial_balance
            
            # Inicializa SessionManager com o saldo
            from src.services.management_3pct import SessionManager
            self.session_manager = SessionManager(self.initial_balance if self.initial_balance > 0 else 100.0)
            logger.info(
                f"[GER] Sessao iniciada: meta diaria=${self.session_manager.daily_target} "
                f"(3x ${self.session_manager.session_target})"
            )
            
            status_text = f"[CHECK] Conectado à {broker_name.upper()} ({'Demo' if is_demo else 'Real'})"
            self.update_live_status(status_text)
            logger.info(f"[CHECK] {status_text}. Saldo: ${self.initial_balance}")
            return True
            
        except Exception as e:
            logger.error(f"[CROSS] Erro ao conectar broker: {e}")
            return False

    def parse_signal(self, text: str) -> dict | None:
        """
        Parser para o formato Patriot:
        🟢 SINAL EURUSD-OTCi CALL
        ⬆️ ENTRADA 18:01 (AGORA)
        🕕 EXPIRAÇÃO 18:02
        ♻️ COM 2G SE NECESSÁRIO
        🕕 Expiração de M1
        """
        raw = text.upper()

        # 1. Direção
        direction = None
        if any(x in raw for x in ["CALL", "\U0001f7e2", "\u2b06\ufe0f", "BUY", "COMPRA"]):
            direction = "CALL"
        elif any(x in raw for x in ["PUT", "\U0001f534", "\u2b07\ufe0f", "SELL", "VENDA"]):
            direction = "PUT"
        if not direction:
            return None

        # 2. Ativo - reconhece qualquer par 4-10 letras,.synthetic, e OTC
        symbol = None

        # 2a. Padrão OTC (IQ Option e sinteticos com sufixo OTC)
        m = re.search(r'([A-Z0-9]{3,10}[-_]OTC[A-Z]?)', raw)
        if m:
            symbol = m.group(1).rstrip("I")
            logger.info(f"[PARSE] Ativo OTC detectado: {symbol}")

        if not symbol:
            # 2b. Sinteticos Deriv: V10, V25, V50, V75, V100, V250, CRASH*, BOOM*, STEP*
            m = re.search(r'\b(V(?:10|25|50|75|100|250)|CRASH(?:1000|500|300|100)|BOOM(?:1000|500|300|100)|STEP(?:10|25|50))\b', raw)
            if m:
                symbol = m.group(1)
                logger.info(f"[PARSE] Sintetico Deriv detectado: {symbol}")

        if not symbol:
            # 2c. Deriv direto: R_10, R_25, 1HZ50V, JD100, etc.
            m = re.search(r'(R_[0-9]{1,3}|1HZ[0-9]{1,3}V|JD[0-9]{1,3})', raw)
            if m:
                symbol = m.group(1)
                logger.info(f"[PARSE] Ativo Deriv detectado: {symbol}")

        if not symbol:
            # 2d. Pares forex sem OTC: EURUSD, GBPUSD, AUDUSD, etc.
            m = re.search(r'\b(EUR|GBP|AUD|NZD|USD|CAD|CHF|JPY|XAU|BTC|ETH)(USD|GBP|JPY|EUR|CHF|CAD|AUD|NZD)\b', raw)
            if m:
                symbol = m.group(0)
                logger.info(f"[PARSE] Par forex detectado: {symbol}")

        if not symbol:
            # 2e. Fallback: qualquer palavra 4-10 letras que pareca ativo financeiro
            skip_words = {
                "SINAL", "ENTRY", "ENTRADA", "EXPIRA", "EXPIRATION",
                "COMPR", "VENDA", "SELL", "BUY", "CALL", "PUT",
                "AGORA", "MARTINGALE", "NECESS", "RECOMEND",
                "ATENCAO", "OPERACAO", "FECHAMENTO", "ABERTURA",
                "ORDEM", "GANHO", "PERDA", "LUCRO", "PREJUIZO",
                "SESSAO", "META", "STOP", "WIN", "LOSS",
                "PAPEL", "MERCADO", "TENDENCIA", "SINALX",
                "TELEGRAM", "SUGESTAO", "ANALISE", "OPERAR",
                "RESULTADO", "CONFIRMA", "AGUARDE", "LIBERADO",
                "DIRECAO", "TIPO", "ATIVO", "PAR", "TEMPO",
                "MINUTO", "HORA", "DIA", "SEMANA", "MES",
                "ROBO", "BOT", "SISTEMA", "PLATAFORMA",
                "RECEITA", "FELIZ", "OBRIGADO", "VALEU",
                "BINARY", "BINARIA", "BINARIAS", "DIGITAL", "DIGITAIS",
                "OPTION", "OPTIONS", "TURBO", "FOREX", "CRYPTO", "CRIPTO",
                "FUTURE", "FUTURES", "FUTURO", "FUTUROS", "PATRIOT", "PATRIOTA",
                "CORRETORA", "CORRETORAS", "SINAIS", "CANAL", "GRUPO",
                "VIP", "PREMIUM", "FREE", "GRATIS", "SUPORTE", "ADM", "ADMIN"
            }
            for m in re.finditer(r'\b([A-Z]{4,10})\b', raw):
                candidate = m.group(1)
                if candidate not in skip_words and not candidate.startswith("EXPIR"):
                    symbol = candidate
                    logger.info(f"[PARSE] Ativo detectado (fallback): {symbol}")
                    break

        if not symbol:
            return None

        # 3. Timeframe (M1, M5, etc.)
        tf = "M1"
        m = re.search(r'(?<![A-Z0-9])M(\d+)(?![A-Z0-9])', raw)
        if m:
            tf = f"M{m.group(1)}"

        # 4. Gales (martingale) - ignorado, usamos nosso gerenciamento
        gales = 0

        # 5. Horário de entrada
        entry_time = None
        m = re.search(r'ENTRADA\s+(\d{1,2}:\d{2})', raw)
        if m:
            entry_time = m.group(1)

        # 6. Horário de expiração
        expiration_time = None
        m = re.search(r'EXPIRA[ÇC][ÃA]O\s+(\d{1,2}:\d{2})', raw)
        if m:
            expiration_time = m.group(1)

        # 7. Duração vem do M1/M5/M15 do sinal
        duration = int(re.search(r'\d+', tf).group()) if re.search(r'\d+', tf) else 1

        # 8. Adaptar símbolo por corretora - so ajusta formato OTC, nao adiciona
        if self.broker_name == "iqoption":
            symbol = symbol.replace("_OTC", "-OTC")
            symbol = re.sub(r'-OTC[A-Z]$', '-OTC', symbol)

        elif self.broker_name in ("deriv", "deriv_demo", "deriv_real"):
            from src.broker.deriv_symbols import resolve_deriv_symbol
            symbol = resolve_deriv_symbol(symbol)

        return {
            "direction": direction,
            "symbol": symbol,
            "timeframe": tf,
            "duration": duration,
            "entry_time": entry_time,
            "expiration_time": expiration_time,
            "gales": gales,
        }


    async def _refresh_balance(self):
        """Atualiza self.current_balance consultando o broker."""
        try:
            if hasattr(self.broker, "async_get_balance"):
                bal = await self.broker.async_get_balance()
            else:
                bal = self.broker.get_balance()
            if bal and bal > 0:
                self.current_balance = bal
                self.session_manager.update_balance(bal)
        except Exception as e:
            logger.warning(f"Falha ao atualizar saldo: {e}")

    async def execute_trade(self, signal):
        if not self.is_running:
            return
        if not self.session_manager:
            logger.error("SessionManager nao inicializado.")
            return

        # Evita ordens consecutivas enquanto vela anterior nao expirou
        if self._order_in_progress:
            logger.info(f"Ordem em andamento. Ignorando novo sinal: {signal['direction']} {signal['symbol']}")
            return

        # Atualiza saldo real do broker antes de calcular entrada
        await self._refresh_balance()
        self.update_live_status(f"Processando sinal: {signal['symbol']}...")

        # Verifica se pode operar (sessao ativa + entradas disponiveis)
        if not self.session_manager.can_trade():
            sm = self.session_manager.get_status()
            if sm["daily_profit"] >= sm["daily_target"]:
                logger.info(f"META DIARIA ATINGIDA! Lucro: ${sm['daily_profit']:.2f} / ${sm['daily_target']:.2f}")
                self.update_live_status(f"META DIARIA ATINGIDA! +${sm['daily_profit']:.2f}")
                self._save_meta_hit()
            else:
                logger.info(f"Todas as 3 sessoes concluidas. Lucro do dia: ${sm['daily_profit']:.2f}")
                self.update_live_status(f"DIA CONCLUIDO. Lucro: ${sm['daily_profit']:.2f}")
            return

        # Verifica stop loss
        if self.initial_balance > 0:
            loss_pct = (self.initial_balance - self.current_balance) / self.initial_balance
            if loss_pct >= self.stop_loss_pct:
                logger.info(f"STOP LOSS {self.stop_loss_pct*100}% ATINGIDO! Loss: ${loss_pct*100:.1f}%")
                self.update_live_status(f"STOP LOSS! Loss: ${loss_pct*100:.1f}%")
                asyncio.create_task(self.stop())
                return

        symbol    = signal["symbol"]
        direction = signal["direction"]
        signal_duration = signal.get("duration", 1)
        duration  = signal_duration
        entry_time = signal.get("entry_time")
        expiration_time = signal.get("expiration_time")

        # Aguardar até 10-15s ANTES DO FECHAMENTO DA VELA (virada)
        # Usa expiration_time do sinal; se não vier, calcula: entry_time + duration minutos
        if entry_time:
            try:
                now = datetime.now()
                
                # Calcula horário de fechamento da vela
                if expiration_time:
                    eh, em = map(int, expiration_time.split(":"))
                    candle_close = now.replace(hour=eh, minute=em, second=0, microsecond=0)
                else:
                    eh, em = map(int, entry_time.split(":"))
                    candle_open = now.replace(hour=eh, minute=em, second=0, microsecond=0)
                    candle_close = candle_open + timedelta(minutes=signal_duration)
                
                # Ajusta para o dia correto se o horário já passou
                if candle_close <= now:
                    candle_close += timedelta(days=1)
                
                # Espera até 10-15 segundos ANTES do fechamento
                antecipacao = random.randint(10, 15)
                target = candle_close - timedelta(seconds=antecipacao)
                wait_secs = (target - now).total_seconds()
                
                if wait_secs > 0:
                    logger.info(f"Vela fecha as {candle_close.strftime('%H:%M:%S')}. Entrando {antecipacao}s antes ({target.strftime('%H:%M:%S')}). Aguardando {wait_secs:.0f}s...")
                    self.update_live_status(f"Aguardando entrada {target.strftime('%H:%M:%S')} ({antecipacao}s antes do fechamento)...")
                    await asyncio.sleep(wait_secs)
            except Exception as e:
                logger.warning(f"Erro ao calcular espera de entrada: {e}")

        self.signals_count += 1
        self.save_state()

        self._order_in_progress = True
        stake = self.session_manager.stake
        sm = self.session_manager.get_status()
        is_deriv = self.broker_name in ("deriv", "deriv_demo", "deriv_real")
        order_duration = 3 if is_deriv else signal_duration
        logger.info(
            f"EXECUTANDO: {direction} {symbol} M{order_duration}"
            f"{' (sinal M' + str(signal_duration) + ')' if is_deriv else ''}"
            f" | Stake: ${stake} ({stake/self.current_balance*100:.1f}% do saldo) | "
            f"Sessao {sm['current_session']}/3 | Entrada {sm['session_entries_used']+1}/3 | "
            f"Lucro: ${sm['daily_profit']:.2f}/{sm['daily_target']:.2f}"
        )
        self.update_live_status(
            f"{direction} {symbol} M{order_duration}"
            f"{' (sinal M' + str(signal_duration) + ')' if is_deriv else ''}"
            f" | Sessao {sm['current_session']} "
            f"(Entrada {sm['session_entries_used']+1}/3) | Stake: ${stake}"
        )

        try:
            self._balance_before_trade = self.broker.get_balance() or self.current_balance
            result = None
            for attempt in range(3):
                try:
                    if self.broker is None:
                        reconnected = await self.connect_broker()
                        if not reconnected:
                            logger.error("Falha ao reconectar broker.")
                            self.update_live_status("Erro: broker desconectado")
                            self._order_in_progress = False
                            return

                    if hasattr(self.broker, "async_send_order"):
                        result = await self.broker.async_send_order(symbol, stake, direction, duration)
                    else:
                        result = self.broker.send_order(symbol, stake, direction, duration)

                    if result and result.get("status") == "ok":
                        break

                    if attempt < 2:
                        err_msg = result.get("result", "") if result else "sem resposta"
                        if any(kw in err_msg.lower() for kw in ["reconect", "conexao", "connect", "timeout", "fechado", "desconectado"]):
                            logger.warning(f"Tentativa {attempt+1}/3: {err_msg}. Reconectando...")
                            try:
                                self.broker.disconnect()
                                self.broker = None
                            except Exception:
                                pass
                            wait_time = 5 + (attempt * 5)
                            logger.info(f"Aguardando {wait_time}s antes de reconectar...")
                            await asyncio.sleep(wait_time)
                            reconnected = await self.connect_broker()
                            if not reconnected:
                                logger.error("Falha ao reconectar broker.")
                                self.update_live_status("Erro: broker desconectado")
                                self._order_in_progress = False
                                return
                            continue
                        else:
                            # Erro que NAO e de conexao (ex: ativo nao encontrado)
                            # Nao reconectar — apenas retry com espera curta
                            wait_time = 2 + (attempt * 2)
                            logger.warning(f"Tentativa {attempt+1}/3: {err_msg}. Retry em {wait_time}s...")
                            await asyncio.sleep(wait_time)
                            continue
                    break
                except Exception as order_err:
                    logger.warning(f"Tentativa {attempt+1}/3 de enviar ordem falhou: {order_err}")
                    if attempt < 2:
                        try:
                            self.broker.disconnect()
                            self.broker = None
                        except Exception:
                            pass
                        wait_time = 5 + (attempt * 5)
                        await asyncio.sleep(wait_time)
                        reconnected = await self.connect_broker()
                        if not reconnected:
                            logger.error("Falha ao reconectar broker.")
                            self.update_live_status("Erro: broker desconectado")
                            self._order_in_progress = False
                            return
                    else:
                        raise

            if result is None or result.get("status") != "ok":
                if result and result.get("status") == "ignored":
                    self._order_in_progress = False
                    return
                logger.error(f"Erro na ordem: {result.get('result') if result else 'no result'}")
                self.update_live_status(f"Erro: {result.get('result') if result else 'ordem falhou'}")
                self._order_in_progress = False
                return

            contract_id = result.get("contract_id") or result.get("order_id")

            if self.broker_name in ("deriv", "deriv_demo", "deriv_real"):
                from src.broker.deriv import DerivBroker
                duration = DerivBroker.DERIV_EXPIRATION_MINUTES

            logger.info(f"Ordem enviada ID:{contract_id}. Aguardando {duration}min...")

            # Salva operacao PENDENTE no dashboard em tempo real
            op_id = str(contract_id or datetime.now().strftime("%H%M%S%f"))
            self._save_pending_operation(symbol, direction, stake, op_id)
            self.update_live_status(f"Ordem enviada: {direction} {symbol} M{order_duration} | Stake: ${stake}")

            await asyncio.sleep(duration * 60 + 3)

            # Verifica resultado
            trade_status = self.broker.get_contract_status(contract_id)
            
            # Se status incerto (error), aguarda 2s para atualizar saldo e tenta novamente
            if trade_status == "error":
                logger.warning(f"Status da ordem {contract_id} incerto. Aguardando saldo...")
                await asyncio.sleep(2)
                trade_status = self.broker.get_contract_status(contract_id)

            self.current_balance = self.broker.get_balance()

            # Se status ainda incerto (error), usa a variação do saldo como arbitro final
            if trade_status == "error":
                logger.warning(f"Status da ordem {contract_id} permaneceu incerto. Usando variação de saldo como arbitro.")
                if self.current_balance > self._balance_before_trade:
                    trade_status = "won"
                else:
                    trade_status = "lost"

            # Calcula lucro/prejuizo
            if trade_status == "won":
                profit = stake * 0.85
                self.success_count += 1
            else:
                profit = -stake

            # Registra no SessionManager e atualiza saldo
            self.session_manager.update_balance(self.current_balance)
            session_result = self.session_manager.register_result(profit)

            msg = f"{'WIN' if trade_status == 'won' else 'LOSS'}! {direction} {symbol} | ${profit:+.2f}"
            logger.info(msg)
            logger.info(
                f"[GER] Sessao {session_result['session']}/3 | "
                f"Entrada {session_result['entry']}/3 | "
                f"Lucro sessao: ${session_result['session_profit']:.2f} | "
                f"Lucro dia: ${session_result['daily_profit']:.2f}/{session_result['daily_target']:.2f}"
            )

            if session_result["session_completed"]:
                logger.info(f"[GER] Sessao {session_result['session']} concluida! Lucro: ${session_result['session_profit']:.2f}")
                if not session_result["all_done"]:
                    logger.info(f"[GER] Avancando para sessao {session_result['next_session']}/3")

            self.save_state()
            self.update_live_status(msg)
            self._resolve_operation(op_id, trade_status, stake, profit)

            # Verifica se dia concluido
            if session_result["all_done"] or session_result.get("daily_goal_hit"):
                final = self.session_manager.get_status()
                logger.info(f"[GER] DIA CONCLUIDO! Lucro total: ${final['daily_profit']:.2f}")
                self.update_live_status(f"DIA CONCLUIDO! Lucro: ${final['daily_profit']:.2f}")
                if final["daily_profit"] >= final["daily_target"]:
                    self._save_meta_hit()

            self._order_in_progress = False

        except Exception as e:
            logger.error(f"Falha na execucao: {e}")
            self.update_live_status(f"Erro: {e}")
            self._order_in_progress = False

    async def _get_db_session_string(self) -> str | None:
        if not self._user_id:
            return None
        try:
            from src.database.session import get_async_session
            from src.models.user import User
            from sqlalchemy import select
            async for db in get_async_session():
                res = await db.execute(select(User.telegram_session_string).where(User.id == self._user_id))
                return res.scalar_one_or_none()
        except Exception as e:
            logger.warning(f"Falha ao carregar telegram_session_string do BD: {e}")
            return None

    async def _clear_db_session_string(self):
        if not self._user_id:
            return
        try:
            from src.database.session import get_async_session
            from src.models.user import User
            from sqlalchemy import select
            async for db in get_async_session():
                res = await db.execute(select(User).where(User.id == self._user_id))
                u = res.scalar_one_or_none()
                if u:
                    u.telegram_session_string = None
                    db.add(u)
                    await db.commit()
                    logger.info(f"StringSession invalida/revogada limpa no banco de dados para usuario {self._user_id}.")
        except Exception as e:
            logger.warning(f"Falha ao limpar telegram_session_string no BD: {e}")

    async def _authenticate_telegram(self):
        """Verifica se o Telegram esta autenticado via StringSession do BD ou sessao local."""
        db_session_str = None
        try:
            db_session_str = await self._get_db_session_string()
            if db_session_str:
                from telethon.sessions import StringSession
                logger.info(f"Carregando StringSession do banco de dados para usuario {self._user_id}...")
                self.client = TelegramClient(
                    StringSession(db_session_str),
                    self.api_id,
                    self.api_hash,
                    auto_reconnect=True,
                    connection_retries=5
                )

            await asyncio.wait_for(self.client.connect(), timeout=25)
            if not await self.client.is_user_authorized():
                logger.error(
                    "Sessao Telegram nao autenticada ou revogada. "
                    "Por favor, conecte a sua conta Telegram diretamente pelo Dashboard da plataforma."
                )
                if self._user_id and db_session_str:
                    await self._clear_db_session_string()
                return False
            logger.info("Telegram autenticado com sucesso.")
            return True
        except asyncio.TimeoutError:
            logger.error("Timeout ao conectar no Telegram.")
            return False
        except Exception as e:
            logger.error(f"Erro ao autenticar Telegram: {e}")
            if self._user_id and db_session_str:
                await self._clear_db_session_string()
            return False

    def _write_pid(self):
        import os
        try:
            with open("copier.pid", "w") as f:
                f.write(str(os.getpid()))
        except Exception:
            pass

    async def _try_reconnect_all(self, attempt: int) -> bool:
        """Tenta reconectar broker + Telegram. Retorna True se ambos ok."""
        logger.info(f"Tentativa {attempt}/3 de reconexao geral...")
        self.update_live_status(f"Reconectando... tentativa {attempt}/3")

        # Reconecta broker
        try:
            self.broker = None
            await asyncio.sleep(2)
            broker_ok = await asyncio.wait_for(self.connect_broker(), timeout=60)
        except Exception as e:
            logger.warning(f"Reconexao broker falhou: {e}")
            broker_ok = False

        if not broker_ok:
            return False

        # Reconecta Telegram
        try:
            await asyncio.wait_for(self.client.connect(), timeout=15)
            authed = await self.client.is_user_authorized()
            if not authed:
                logger.warning("Telegram perdeu autenticacao apos queda")
                return False
        except Exception as e:
            logger.warning(f"Reconexao Telegram falhou: {e}")
            return False

        logger.info(f"Reconexao geral bem-sucedida (tentativa {attempt}/3)")
        self.update_live_status("Reconectado com sucesso. Aguardando sinais...")
        return True

    async def _reconnect_loop(self):
        """Loop principal com reconexao automatica em caso de queda."""
        max_attempts = 3
        while self.is_running:
            try:
                await self.client.run_until_disconnected()
            except Exception as e:
                logger.warning(f"Conexao perdida: {e}")

            if not self.is_running:
                break

            if self._reconnect_lock.locked():
                logger.info("[RECONNECT] Heartbeat ja esta reconectando — pulando.")
                continue

            async with self._reconnect_lock:
                logger.warning("Iniciando sequencia de reconexao...")
                reconnected = False
                for attempt in range(1, max_attempts + 1):
                    if await self._try_reconnect_all(attempt):
                        reconnected = True
                        break
                    wait = attempt * 10
                    logger.info(f"Aguardando {wait}s antes da tentativa {attempt+1}/3...")
                    self.update_live_status(f"Reconexao {attempt}/3 falhou. Nova tentativa em {wait}s...")
                    await asyncio.sleep(wait)

                if not reconnected:
                    logger.error("3 tentativas de reconexao falharam. Bloqueando copier.")
                    self.update_live_status("BLOQUEADO: sem conexao. Reative manualmente no painel.")
                    self._blocked = True
                    break

    async def _heartbeat(self):
        """Verifica a cada N segundos se broker e Telegram ainda estao respondendo."""
        while self.is_running and not self._blocked:
            await asyncio.sleep(self._heartbeat_interval)
            if not self.is_running or self._blocked:
                break
            if self._reconnect_lock.locked():
                continue  # ja esta reconectando, pula
            async with self._reconnect_lock:
                try:
                    # Testa se o broker responde com saldo e atualiza em tempo real
                    bal = self.broker.get_balance()
                    if bal is None:
                        logger.warning("[HEARTBEAT] Broker sem resposta — iniciando reconexao.")
                        await self._try_reconnect_all(1)
                        continue
                    if bal > 0 and abs(bal - self.current_balance) > 0.005:
                        self.current_balance = bal
                        if self.session_manager:
                            self.session_manager.update_balance(bal)
                        self.update_live_status(f"Saldo atualizado: ${bal:.2f}")
                        logger.info(f"[HEARTBEAT] Saldo atualizado em tempo real: ${bal:.2f}")
                except Exception as e:
                    logger.warning(f"[HEARTBEAT] Broker falhou ({e}) — reiniciando conexao.")
                    await self._try_reconnect_all(1)
                    continue

                try:
                    # Testa se o Telegram ainda esta conectado
                    if self.client and self.client.is_connected():
                        authed = await self.client.is_user_authorized()
                        if not authed:
                            logger.warning("[HEARTBEAT] Telegram perdeu autenticacao — reconectando.")
                            await self._try_reconnect_all(1)
                    else:
                        logger.warning("[HEARTBEAT] Telegram desconectado — reconectando.")
                        await self._try_reconnect_all(1)
                except Exception as e:
                    logger.warning(f"[HEARTBEAT] Telegram falhou ({e}) — reconectando.")
                    await self._try_reconnect_all(1)

    async def start(self):
        self._blocked = False
        self.load_state()
        self._load_risk_config()

        # Verifica se a meta ja foi batida hoje (auto-lock)
        if self._check_meta_lock():
            self.update_live_status("Meta diaria ja atingida. Copier bloqueado.")
            return

        broker_ok = False
        last_err = ""
        for attempt in range(1, 4):
            try:
                broker_ok = await asyncio.wait_for(self.connect_broker(), timeout=60)
            except asyncio.TimeoutError:
                logger.error(f"Timeout ao conectar broker (60s). Tentativa {attempt}/3.")
                last_err = "Timeout ao conectar broker"
                broker_ok = False
            except Exception as e:
                logger.error(f"Erro ao conectar broker: {e}. Tentativa {attempt}/3.")
                last_err = str(e)
                broker_ok = False
            if broker_ok:
                break
            if attempt < 3:
                logger.info(f"Aguardando 10s antes da proxima tentativa...")
                self.update_live_status(f"Falha ao conectar broker (tentativa {attempt}/3). Reconectando...")
                await asyncio.sleep(10)

        if not broker_ok:
            self.update_live_status(f"Erro: nao foi possivel conectar ao broker. {last_err}")
            return

        # PID so e escrito apos broker conectar com sucesso
        self._write_pid()
        
        self.update_live_status("Autenticando no Telegram...")
        
        if not await self._authenticate_telegram():
            self.update_live_status("Erro: falha na autenticacao Telegram")
            return
        
        self.is_running = True
        self.update_live_status("Aguardando sinais da sala...")

        # Lista canais monitorados no log de startup
        try:
            dialogs = await self.client.get_dialogs(limit=50)
            channels_info = [f"'{d.name}'" for d in dialogs if d.is_channel or d.is_group]
            if channels_info:
                logger.info(f"[TELEGRAM] Monitorando {len(channels_info)} canais/grupos: {', '.join(channels_info[:10])}")
        except Exception as e:
            logger.debug(f"Falha ao listar canais: {e}")

        @self.client.on(events.NewMessage(chats=self.target_chats))
        async def handler(event):
            try:
                text = event.message.text
                if not text: return
                
                chat_title = "Chat Desconhecido"
                try:
                    chat = await event.get_chat()
                    chat_title = getattr(chat, 'title', None) or getattr(chat, 'first_name', None) or f"ID:{event.chat_id}"
                except Exception:
                    chat_title = f"ID:{event.chat_id}"

                logger.info(f"📨 MSG RECEBIDA de [{chat_title}]: {text[:200]}")

                raw = text.upper()
                if any(kw in raw for kw in ["WIN DE PRIMEIRA", "LOSS", "GANHO", "PERDA", "RESULTADO"]):
                    if "SINAL" not in raw:
                        logger.info(f"[PARSE] Mensagem de resultado ignorada")
                        return

                signal = self.parse_signal(text)
                if signal:
                    await self.execute_trade(signal)
            except Exception as e:
                logger.error(f"Erro no handler: {e}")

        # Inicia heartbeat em background (ping a cada 30s)
        heartbeat_task = asyncio.create_task(self._heartbeat())

        await self._reconnect_loop()

        heartbeat_task.cancel()

    async def stop(self):
        """Encerra completamente o copier, salvando estado e fechando todas as conexoes."""
        self.is_running = False
        
        # Salva estado atual antes de encerrar
        try:
            self.save_state()
            logger.info("[COPPER] Estado salvo antes de encerrar.")
        except Exception as e:
            logger.warning(f"[COPPER] Erro ao salvar estado antes de parar: {e}")
        
        # Encerra conexoes em ordem correta
        if self.client:
            try:
                await self.client.disconnect()
                logger.info("[COPPER] Conexao Telegram encerrada.")
            except Exception as e:
                logger.warning(f"[COPPER] Erro ao encerrar conexao Telegram: {e}")
        
        if self.broker:
            try:
                self.broker.disconnect()
                logger.info("[COPPER] Conexao Broker encerrada.")
            except Exception as e:
                logger.warning(f"[COPPER] Erro ao encerrar conexao Broker: {e}")
        
        logger.info("[COPPER] Copier encerrado completamente.")


if __name__ == "__main__":
    import sys
    import uuid
    user_id = None
    broker_name = None
    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == "--user-id" and i + 1 < len(args):
            try:
                user_id = uuid.UUID(args[i + 1])
            except:
                pass
        elif arg == "--broker" and i + 1 < len(args):
            broker_name = args[i + 1]
    copier = TelegramCopier(user_id=user_id, broker_name=broker_name)
    try:
        asyncio.run(copier.start())
    except KeyboardInterrupt:
        logger.info("Encerrando...")
