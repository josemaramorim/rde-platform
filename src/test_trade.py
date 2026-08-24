"""
Script de Teste de Execução de Trade - RDE Platform
Simula a chegada de um sinal e executa na corretora configurada.
"""
import asyncio
import logging
from src.database.session import SessionLocal
from src.models.user import User
from src.executor import execute_trade

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger("RDE-Test")

async def test_manual_trade():
    db = SessionLocal()
    try:
        # 1. Busca o usuario
        email = "ferreira.jpa1@hotmail.com"
        user = db.query(User).filter(User.email == email).first()
        
        if not user:
            print(f"\n❌ ERRO: Usuario '{email}' nao encontrado.")
            print("Execute primeiro: python -m src.create_admin\n")
            return

        print(f"\n--- 🤖 INICIANDO TESTE DE TRADE ---")
        print(f"👤 Usuario: {user.email}")
        print(f"🏦 Corretora: {user.broker.upper()}")
        print(f"💰 Stake: ${user.stake}")
        
        # 2. Pergunta a direcao
        direcao = input("\nEscolha a direção para o teste (CALL/PUT): ").strip().upper()
        if direcao not in ["CALL", "PUT"]:
            print("Direção inválida. Use CALL ou PUT.")
            return

        print(f"\n🚀 Enviando ordem de {direcao}...")

        # 3. Executa o trade (Chama toda a logica oficial do sistema)
        # Passamos o DB para ele persistir o lucro/loss e o proximo gale
        result = execute_trade(user, direcao, db)
        
        # Salva as alteracoes no banco (lucro e novo gale)
        db.commit()

        print("\n--- 📊 RESULTADO DO TESTE ---")
        if "error" in result:
            print(f"❌ FALHA: {result['error']}")
        else:
            outcome = result['outcome'].upper()
            color = "✅" if outcome == "WIN" else "❌"
            print(f"{color} RESULTADO: {outcome}")
            print(f"💵 Lucro Total Atual: ${result['total_profit']}")
            print(f"📈 Proxima Stake: ${result['next_stake']}")
            print(f"📝 Resposta Corretora: {result['broker_response']}")

    except Exception as e:
        logger.error(f"Erro inesperado no teste: {e}")
    finally:
        db.close()
        print("\n--- TESTE FINALIZADO ---\n")

if __name__ == "__main__":
    asyncio.run(test_manual_trade())
