"""
Script para alternar entre as corretoras (Deriv, IQ Option).
Uso: python -m src.switch_broker [deriv|iqoption] [demo|real]
"""
import sys
import asyncio
from src.database.session import SessionLocal
from src.models.user import User
from src.models.broker import BrokerSetting

async def switch_broker():
    if len(sys.argv) < 2:
        print("\n❌ Erro: Especifique a corretora. Ex: python -m src.switch_broker iqoption")
        return

    broker_name = sys.argv[1].lower()
    mode = sys.argv[2].lower() if len(sys.argv) > 2 else "demo"
    is_demo = (mode == "demo")
    
    valid_brokers = ["deriv", "iqoption"]
    if broker_name not in valid_brokers:
        print(f"❌ Erro: Corretora inválida. Escolha: {', '.join(valid_brokers)}")
        return

    db = SessionLocal()
    try:
        # 1. Busca o usuario ADM
        email = "ferreira.jpa1@hotmail.com"
        user = db.query(User).filter(User.email == email).first()
        
        if not user:
            print(f"❌ Erro: Usuario '{email}' nao encontrado.")
            return

        # 2. Desativa todas as corretoras e ativa a escolhida
        stmt = db.query(BrokerSetting).filter(BrokerSetting.user_id == user.id).all()
        
        target_found = False
        for setting in stmt:
            if setting.broker_name == broker_name:
                setting.is_active = True
                setting.is_demo = is_demo
                target_found = True
            else:
                setting.is_active = False
        
        if not target_found:
            print(f"⚠️ Aviso: Nenhuma configuração prévia para '{broker_name}' no banco. Rode o setup_brokers primeiro.")
            return

        # Atualiza campo legado
        user.broker = broker_name
        
        db.commit()
        
        print("\n" + "="*40)
        print(f"✅ CORRETORA ALTERADA COM SUCESSO!")
        print(f"🌍 Ativa: {broker_name.upper()}")
        print(f"📊 Modo: {'🎮 DEMO' if is_demo else '💰 REAL'}")
        print("="*40)
        print("\n🚀 Agora pode rodar: python -m src.telegram_copier\n")

    except Exception as e:
        print(f"❌ Erro ao trocar broker: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(switch_broker())
