"""
Exemplos de uso do pool de conexões WebSocket multi-corretora
"""

from services.websocket_pool_multi_broker import (
    Broker,
    get_connection,
    close_connection,
    close_all_for_broker,
    close_all,
    get_pool_status,
)
import json
import logging

logging.basicConfig(level=logging.INFO)

# ============================================================================
# EXEMPLO 1: Conexão IQ Option (padrão)
# ============================================================================

def example_iqoption():
    """Exemplo básico com IQ Option."""
    api_token = "seu_token_iqoption_aqui"
    
    try:
        # Obtém conexão (cria nova ou reutiliza existente)
        ws = get_connection(api_token, Broker.IQOPTION)
        
        # Envia comando de trade (exemplo genérico)
        trade_cmd = json.dumps({
            "method": "buyV2",
            "params": {
                "instrument_type": "turbo",
                "side": "call",
                "amount": 10,
                "user_balance_id": 123456,
            }
        })
        ws.send(trade_cmd)
        
        # Recebe resposta
        response = ws.recv()
        print(f"IQ Option Response: {response}")
        
    except ConnectionError as e:
        print(f"Connection error: {e}")
    except Exception as e:
        print(f"Error: {e}")


# ============================================================================
# EXEMPLO 2: Conexão Quotex
# ============================================================================

def example_quotex():
    """Exemplo com Quotex."""
    api_token = "seu_token_quotex_aqui"
    
    try:
        ws = get_connection(api_token, Broker.QUOTEX)
        
        # Trade no Quotex
        trade_cmd = json.dumps({
            "method": "buy",
            "amount": 20,
            "instrument_id": "eur_usd",
            "direction": "call",
            "duration": 60
        })
        ws.send(trade_cmd)
        
        response = ws.recv()
        print(f"Quotex Response: {response}")
        
    except ConnectionError as e:
        print(f"Connection error: {e}")
    except Exception as e:
        print(f"Error: {e}")


# ============================================================================
# EXEMPLO 3: Conexão Pocket Option
# ============================================================================

def example_pocketoption():
    """Exemplo com Pocket Option."""
    api_token = "seu_token_pocketoption_aqui"
    
    try:
        ws = get_connection(api_token, Broker.POCKETOPTION)
        
        # Trade no Pocket Option
        trade_cmd = json.dumps({
            "method": "trade",
            "params": {
                "asset": "EURUSD",
                "amount": 15,
                "direction": "call",
                "duration": 60
            }
        })
        ws.send(trade_cmd)
        
        response = ws.recv()
        print(f"Pocket Option Response: {response}")
        
    except ConnectionError as e:
        print(f"Connection error: {e}")
    except Exception as e:
        print(f"Error: {e}")


# ============================================================================
# EXEMPLO 4: Múltiplas Corretoras Simultâneas
# ============================================================================

def example_multi_broker():
    """Usa múltiplas corretoras ao mesmo tempo."""
    
    tokens = {
        Broker.IQOPTION: "token_iqoption",
        Broker.QUOTEX: "token_quotex",
        Broker.POCKETOPTION: "token_pocketoption",
    }
    
    try:
        # Conecta a todas
        connections = {}
        for broker, token in tokens.items():
            ws = get_connection(token, broker)
            connections[broker] = ws
            print(f"✓ Conectado ao {broker.value}")
        
        # Verifica status do pool
        status = get_pool_status()
        print(f"\nStatus do pool: {status}")
        
        # Faz trade em cada uma
        for broker, ws in connections.items():
            # Aqui você colocaria a lógica de trade específica de cada corretora
            print(f"Enviando comando para {broker.value}...")
            # ws.send(...)
            
    except Exception as e:
        print(f"Error: {e}")


# ============================================================================
# EXEMPLO 5: Reutilização de Conexões
# ============================================================================

def example_connection_reuse():
    """Demonstra reutilização de conexão persistente."""
    api_token = "seu_token_aqui"
    broker = Broker.IQOPTION
    
    try:
        # Primeira chamada: cria nova conexão
        print("Primeira chamada...")
        ws1 = get_connection(api_token, broker)
        print(f"Conexão criada: {id(ws1)}")
        
        # Segunda chamada: reutiliza mesma conexão
        print("\nSegunda chamada...")
        ws2 = get_connection(api_token, broker)
        print(f"Conexão reutilizada: {id(ws2)}")
        
        # Verifica se são o mesmo objeto
        if id(ws1) == id(ws2):
            print("✓ Mesma conexão reutilizada!")
        
    except Exception as e:
        print(f"Error: {e}")


# ============================================================================
# EXEMPLO 6: Gerenciamento de Shutdown
# ============================================================================

def example_shutdown():
    """Exemplo de shutdown adequado."""
    
    try:
        # Cria várias conexões
        tokens = {
            Broker.IQOPTION: "token1",
            Broker.QUOTEX: "token2",
            Broker.POCKETOPTION: "token3",
        }
        
        for broker, token in tokens.items():
            get_connection(token, broker)
            print(f"Conectado: {broker.value}")
        
        # Mostra status
        status = get_pool_status()
        print(f"\nConexões ativas: {status}")
        
        # Fecha todas de uma corretora
        print("\nFechando todas as conexões IQ Option...")
        close_all_for_broker(Broker.IQOPTION)
        
        # Mostra novo status
        status = get_pool_status()
        print(f"Conexões ativas: {status}")
        
        # Fecha tudo
        print("\nFechando todas as conexões...")
        close_all()
        status = get_pool_status()
        print(f"Conexões ativas: {status}")
        
    except Exception as e:
        print(f"Error: {e}")


# ============================================================================
# EXEMPLO 7: Tratamento de Erros
# ============================================================================

def example_error_handling():
    """Demonstra tratamento de erros."""
    
    # Token inválido
    try:
        ws = get_connection("invalid_token_123", Broker.IQOPTION)
    except ConnectionError as e:
        print(f"Erro esperado: {e}")
    
    # Corretora não existente (descomentar se adicionar mais)
    # try:
    #     from websocket_pool_multi_broker import Broker
    #     ws = get_connection("token", Broker.NONEXISTENT)
    # except ValueError as e:
    #     print(f"Erro esperado: {e}")


# ============================================================================
# EXEMPLO 8: Integration com sistema de trading
# ============================================================================

class MultibrokerTrader:
    """Classe para gerenciar trading em múltiplas corretoras."""
    
    def __init__(self):
        self.active_brokers = {}
    
    def connect(self, broker: Broker, api_token: str):
        """Conecta a uma corretora."""
        try:
            ws = get_connection(api_token, broker)
            self.active_brokers[broker] = {
                "token": api_token,
                "ws": ws
            }
            print(f"✓ Conectado ao {broker.value}")
        except ConnectionError as e:
            print(f"✗ Falha ao conectar {broker.value}: {e}")
    
    def trade(self, broker: Broker, **kwargs):
        """Executa trade em uma corretora específica."""
        if broker not in self.active_brokers:
            print(f"Não conectado ao {broker.value}")
            return
        
        ws = self.active_brokers[broker]["ws"]
        try:
            # Aqui você implementaria a lógica específica de cada corretora
            trade_cmd = json.dumps(kwargs)
            ws.send(trade_cmd)
            response = ws.recv()
            print(f"{broker.value} - Resposta: {response}")
        except Exception as e:
            print(f"Erro ao fazer trade: {e}")
    
    def disconnect_all(self):
        """Desconecta de todas as corretoras."""
        for broker in self.active_brokers.keys():
            close_all_for_broker(broker)
        self.active_brokers.clear()
        print("Desconectado de todas as corretoras")
    
    def status(self):
        """Mostra status das conexões."""
        return get_pool_status()


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    
    # Descomente o exemplo que deseja executar:
    
    # example_iqoption()
    # example_quotex()
    # example_pocketoption()
    # example_multi_broker()
    # example_connection_reuse()
    # example_shutdown()
    # example_error_handling()
    
    # Usar classe MultibrokerTrader
    print("=== Exemplo: MultibrokerTrader ===\n")
    trader = MultibrokerTrader()
    
    # Conecta a múltiplas corretoras
    trader.connect(Broker.IQOPTION, "seu_token_iqoption")
    trader.connect(Broker.QUOTEX, "seu_token_quotex")
    trader.connect(Broker.POCKETOPTION, "seu_token_pocketoption")
    
    print(f"\nStatus: {trader.status()}\n")
    
    # Faz trades
    # trader.trade(Broker.IQOPTION, method="buyV2", amount=10)
    # trader.trade(Broker.QUOTEX, method="buy", amount=20)
    
    # Desconecta
    trader.disconnect_all()