@echo off
cd /d F:\RDE

echo Verificando integridade do banco...
if exist "rde_local.db" (
    python -c "import sqlite3; c=sqlite3.connect('rde_local.db'); c.execute('PRAGMA wal_checkpoint(TRUNCATE)'); c.execute('PRAGMA integrity_check'); r=c.fetchall(); c.close(); print('DB:', 'OK' if all(x[0]=='ok' for x in r) else 'FALHA')" 2>nul
)

set PYTHONPATH=F:\RDE
set RDE_PROFILE=admin
set PYTHON=C:\Users\ferre\AppData\Local\Programs\Python\Python312\python.exe
start "" /min cmd /c "%PYTHON% -m uvicorn src.main:app --host 0.0.0.0 --port 8000 --no-access-log >> F:\RDE\backend.log 2>> F:\RDE\backend_err.log"
echo Backend iniciado na porta 8000.
