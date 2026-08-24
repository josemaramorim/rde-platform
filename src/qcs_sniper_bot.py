import time
import asyncio
import logging
from datetime import datetime
from broker import iqoption
from src.database.session import SessionLocal
from src.models.user import User
from src.models.broker import BrokerSetting
from src.broker.iqoption import IQOptionBroker
from src.strategies.sniper import RDESniperStrategy

# Configuração de Logs
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("rde_sniper")

class QCSSniperBot:
    def __init__(self, email="ferreira.jpa1@hotmail.com"):
        self.email = email
        self.broker = iqoption 
        self.strategy = RDESniperStrategy(bb_period=20, bb_dev=2.5, rsi_period=4)
        
        # Pares famosos de Forex e OTC para monitorar (Você pode adicionar/remover)
        self.assets_to_monitor = [
            "EURUSD", "GBPUSD", "USDJPY", "EURJPY-OTC", "USDCHF-OTC",
            "EURUSD-OTC", "GBPUSD-OTC"
        ]

    def setup(self):
        db = SessionLocal()
        user = db.query(User).filter(User.email == self.email).first()
        
        if not user:
            logger.error("❌ Usuário não encontrado!")
            return False

        # Verifica o broker ativo
        active_setting = None
        for setting in user.broker_settings:
            if setting.is_active:
                active_setting = setting
                break

        from src.core.security import encryption_service
        
        # Função helper igual a do telegram_copier
        def _decrypt(val):
            if not val:
                return None
            try:
                dec = encryption_service.decrypt(val)
                return dec if dec != "ERROR_DECRYPT" else val
            except:
                return val

        email_to_use = active_setting.email or user.iq_email
        pass_to_use = _decrypt(active_setting.password) or user.iq_password
        api_token_to_use = _decrypt(active_setting.api_token)
        
        if api_token_to_use and "@" in api_token_to_use:
            email_to_use = api_token_to_use
            # Se a senha estava vazia ou diferente no token, ideal manter a password descritografada

        logger.info("⚙️ Iniciando Sniper Engine na IQ OPTION...")
        self.broker = IQOptionBroker(
            email=email_to_use,
            password=pass_to_use,
            is_demo=active_setting.is_demo
        )

        try:
            self.broker.connect()
            balance = self.broker.get_balance()
            self.initial_balance = balance
            logger.info(f"✅ ✅ Conectado! Saldo Inicial do Dia: ${self.initial_balance}")
            return True
        except Exception as e:
            logger.error(f"❌ Erro ao conectar: {e}")
            return False

    def get_market_data(self, asset):
        """Baixa as últimas 30 velas de 1 Minuto"""
        try:
            # Parametros: ativo, intervalo(s), quantidade, _fim_de_tempo
            candles = self.broker.api.get_candles(asset.replace("-OTC", ""), 60, 30, time.time())
            
            # Limpa e converte o formato da iqoptionapi para nossa estrategia abstrata
            formatted_candles = []
            for c in candles:
                formatted_candles.append({
                    "open": c["open"],
                    "close": c["close"],
                    "high": c["max"],
                    "low": c["min"]
                })
            return formatted_candles
        except Exception as e:
            logger.warning(f"⚠️ Erro ao obter dados do ativo {asset}: Nao disponivel no momento.")
            return None

    def run(self):
        """Loop Principal de Scanner de Sinais"""
        if not self.setup():
            return

        logger.info(f"🤖 Scanner Ativado. Monitorando {len(self.assets_to_monitor)} ativos.")
        logger.info("🔎 Estrutura de análise: BB(20, 2.5) + RSI(4)")

        while True:
            now = datetime.now()
            
            # Executa a verificação sempre no segundo 58 (2 segundos antes da vela fechar)
            # Para entrar pontualmente na abertura da proxima!
            if now.second == 58:
                logger.info(f"⏳ Passando Scanner de Reversão... ({now.strftime('%H:%M')})")
                
                for asset in self.assets_to_monitor:
                    # Filtro de Gerenciamento 3% (Planilha Mágica)
                    
                    try:
                        current_balance = self.broker.get_balance()
                        profit_so_far = current_balance - self.initial_balance
                        meta_diaria = self.initial_balance * 0.01  # Meta de Sessão: 1%
                        
                        if profit_so_far >= meta_diaria:
                            logger.info(f"🎯 META DE SESSÃO (1%) BATIDA! Lucro: ${profit_so_far:.2f} / Meta: ${meta_diaria:.2f}")
                            logger.info("🔒 Segurança Ativa: Fechando a inteligência para evitar exposição a notícias/queda de rede.")
                            logger.info("Ligue o robô novamente apenas na próxima Sessão (Tarde ou Noite)!")
                            time.sleep(999999) 
                            return
                    except Exception as e:
                        pass # ignora erro de balance
                        
                    candles = self.get_market_data(asset)
                    
                    if not candles:
                        continue
                        
                    signal = self.strategy.analyze(candles)
                    
                    if signal:
                        logger.info(f"🚨🚨 ALERTA CRÍTICO: PADRÃO DETECTADO EM {asset} 🚨🚨")
                        logger.info(f"🚀 EXECUTANDO ORDEM AUTOMÁTICA: {signal.upper()} no par {asset}")
                        
                        # Executa ordem de $2 para teste
                        res = self.broker.send_order(symbol=asset, stake=2.0, direction=signal)
                        if res['status'] == 'ok':
                            logger.info(f"✅ Trade aberto com sucesso! ID: {res.get('order_id')}")
                        else:
                            logger.error(f"❌ Não foi possivel abrir o trade em {asset}.")
                        
                        time.sleep(1) # Intervalo seguro

                # Espera uns segundos para não verificar de novo no mesmo minuto
                time.sleep(2) 
            
            # Sleeper super rápido para testar o segundo correto
            time.sleep(0.5)

if __name__ == "__main__":
    bot = QCSSniperBot()
    try:
        bot.run()
    except KeyboardInterrupt:
        logger.info("🛑 Scanner Desligado pelo USUÁRIO.")
