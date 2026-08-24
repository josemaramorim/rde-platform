@echo off
cd /d "%~dp0"

>nul 2>&1 net session || (
    echo ====================================
    echo   Elevando para Administrador...
    echo ====================================
    timeout /t 1 /nobreak >nul
    powershell start -verb runas '%~f0' 2>nul
    exit /b
)

echo ====================================
echo   RDE Platform - Iniciando...
echo ====================================
echo.

echo [1/7] Encerrando processos antigos...
>nul 2>&1 taskkill /F /IM python.exe
>nul 2>&1 taskkill /F /IM node.exe
>nul 2>&1 taskkill /F /IM redis-server.exe
REM Mata processo na porta 8000 (se ainda estiver vivo)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr /R ":8000 " ^| findstr /R "LISTENING"') do (
    >nul 2>&1 taskkill /F /PID %%a
)
REM Mata processo na porta 3000 (se ainda estiver vivo)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr /R ":3000 " ^| findstr /R "LISTENING"') do (
    >nul 2>&1 taskkill /F /PID %%a
)
REM Mata processo na porta 6379 (se ainda estiver vivo)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr /R ":6379 " ^| findstr /R "LISTENING"') do (
    >nul 2>&1 taskkill /F /PID %%a
)
echo OK

echo [2/7] Limpando caches...
if exist "C:\rde-frontend\.next" rd /s /q "C:\rde-frontend\.next"
if exist "C:\rde-frontend\out" rd /s /q "C:\rde-frontend\out"
for /d /r "%~dp0src" %%d in (__pycache__) do if exist "%%d" rd /s /q "%%d"
echo OK

echo [3/7] Ativando ambiente virtual...
call .venv\Scripts\activate.bat
echo OK

echo [4/7] Inicializando banco de dados...
python -c "import sys; sys.path.insert(0, '.'); from src.database.session import sync_engine; from src.models.user import Base; from src.models.broker import Base as BBase; Base.metadata.create_all(bind=sync_engine); BBase.metadata.create_all(bind=sync_engine); print('DB OK')"
python -c "import sys; sys.path.insert(0, '.'); from src.seed_plans import seed; seed()"
echo OK

echo [5/7] Iniciando Redis (Porta 6379)...
start "RDE Redis" cmd /k "redis-server"
timeout /t 2 /nobreak
echo OK

echo [6/7] Iniciando Backend (FastAPI na Porta 8000)...
start "RDE Backend" cmd /k "call .venv\Scripts\activate.bat && set PYTHONPATH=F:\RDE && set RDE_PROFILE=admin && python -m uvicorn src.main:app --reload --host 0.0.0.0 --port 8000"
timeout /t 3 /nobreak
echo OK

echo [7/7] Iniciando Frontend (Next.js na Porta 3000)...
if exist "C:\rde-frontend" (
    start "RDE Frontend" cmd /k "cd /d C:\rde-frontend && npm run dev"
    echo Frontend iniciado em http://localhost:3000
)
echo.

echo ====================================
echo   RDE Platform PRONTA!
echo ====================================
echo   API:  http://localhost:8000
echo   Docs: http://localhost:8000/docs
echo   Front: http://localhost:3000
echo ====================================
echo.
start http://localhost:3000
pause
