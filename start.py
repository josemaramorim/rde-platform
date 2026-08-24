import os
import sys

# Garante que /app esteja no PYTHONPATH para encontrar uvicorn e demais pacotes
sys.path.insert(0, "/app")
os.environ["PYTHONPATH"] = "/app"

# Executa uvicorn substituindo o processo atual
os.execvp(
    sys.executable,
    [
        sys.executable, "-m", "uvicorn",
        "src.main:app",
        "--host", "0.0.0.0",
        "--port", "8000",
    ],
)
