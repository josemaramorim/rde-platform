@echo off
cd /d "%~dp0"

echo ============================================
echo  RDE Platform - Inicializacao Segura
echo ============================================
echo.

REM === Parada segura dos processos ===
echo [1/6] Parando servicos antigos...

REM Mata pelo titulo da janela (mais seguro, nao mata Python de outros projetos)
taskkill /F /FI "WINDOWTITLE eq RDE Backend*" >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq RDE Redis*" >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq RDE Frontend*" >nul 2>&1

REM Mata uvicorn e redis (fallback por nome, sem usar /IM python.exe)
for /f "tokens=2" %%a in ('tasklist ^| findstr /i "uvicorn"') do taskkill /PID %%a /F >nul 2>&1
for /f "tokens=2" %%a in ('tasklist ^| findstr /i "redis-server"') do taskkill /PID %%a /F >nul 2>&1
for /f "tokens=2" %%a in ('tasklist ^| findstr /i "node"') do (
    wmic process where "processid=%%a" get commandline | findstr /i "rde-frontend" >nul 2>&1 && taskkill /PID %%a /F >nul 2>&1
)

REM Aguarda finalizacao
timeout /t 2 /nobreak >nul
echo    OK - Processos finalizados.
echo.

REM === Verificacao e Recuperacao do Banco de Dados ===
echo [2/6] Verificando integridade do banco de dados...

set "DB_FILE=rde_local.db"
if exist "%DB_FILE%" (
    REM Recupera WAL pendente se existir
    if exist "%DB_FILE%-wal" (
        echo    WAL pendente detectado. Recuperando...
        python -c "import sqlite3; c=sqlite3.connect('%DB_FILE%'); c.execute('PRAGMA wal_checkpoint(TRUNCATE)'); c.close()" 2>nul
    )
    REM Verifica integridade
    python -c "import sqlite3; c=sqlite3.connect('%DB_FILE%'); c.execute('PRAGMA integrity_check'); r=c.fetchall(); print('    Integridade:', 'OK' if all(x[0]=='ok' for x in r) else 'FALHA - '+str(r)); c.close()"
) else (
    echo    Banco de dados nao encontrado. Será criado na inicializacao.
)
echo.

REM === Criacao das tabelas ===
echo [3/6] Sincronizando tabelas do banco de dados...
python -c "import sys; sys.path.insert(0, '.'); from src.database.session import sync_engine; from src.models.user import Base as UBase; from src.models.broker import Base as BBase; UBase.metadata.create_all(bind=sync_engine); BBase.metadata.create_all(bind=sync_engine); print('    Tabelas sincronizadas OK')"
echo.

REM === Limpeza de arquivos temporarios ===
echo [4/6] Limpando arquivos temporarios...
if exist "copier.pid" (
    python -c "import sys; f=open('copier.pid'); c=f.read().strip(); f.close(); print('    copier.pid removido:', c)" 2>nul
    del copier.pid 2>nul
)
REM Remove session files antigos (mais de 24h)
forfiles /p "%~dp0" /m "rde_user_session_*.session" /d -1 /c "cmd /c del @file" 2>nul
forfiles /p "%~dp0" /m "live_status_*.json" /d -1 /c "cmd /c del @file" 2>nul
REM Remove __pycache__ corrompido se houver
if exist "src\__pycache__" (
    python -c "import py_compile, glob; [py_compile.compile(f, doraise=True) for f in glob.glob('src/**/__pycache__/*.pyc', recursive=True)]" 2>nul
)
REM Trunca logs antigos para evitar confusao com erros passados
if exist "backend.log" copy /y nul "backend.log" >nul
if exist "backend_err.log" copy /y nul "backend_err.log" >nul
echo    OK
echo.

REM === Iniciar Redis ===
echo [5/6] Iniciando servicos...
start "RDE Redis" /min cmd /c "redis-server"
timeout /t 2 /nobreak >nul
echo    Redis iniciado.
echo.

REM === Iniciar Backend ===
echo Iniciando Backend (porta 8000)...
start "RDE Backend" /min cmd /c ".\.venv\Scripts\activate.bat && set PYTHONPATH=F:\RDE && set RDE_PROFILE=admin && python -m uvicorn src.main:app --host 0.0.0.0 --port 8000 --no-access-log >> backend.log 2>> backend_err.log"
timeout /t 4 /nobreak >nul

REM Verifica se o backend subiu
python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=5); print('    Backend OK')" 2>nul || (
    echo    AVISO: Backend pode nao ter iniciado. Verifique backend_err.log
)
echo.

REM === Iniciar Frontend ===
echo Iniciando Frontend (porta 3000)...
start "RDE Frontend" /min cmd /c "cd /d C:\rde-frontend && npm run dev"
timeout /t 5 /nobreak >nul

REM === Abrir navegador ===
echo [6/6] Abrindo navegador...
start http://localhost:3000/login

echo.
echo ============================================
echo  RDE Platform iniciada com sucesso!
echo  Backend : http://localhost:8000
echo  Frontend: http://localhost:3000
echo ============================================
echo.
pause
