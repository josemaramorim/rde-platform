@echo off
cd /d "%~dp0"
echo ============================================
echo  RDE - Recuperacao de Banco de Dados
echo ============================================
echo.

REM Para todos os processos que usam o banco
echo [1/4] Parando servicos...
taskkill /F /FI "WINDOWTITLE eq RDE Backend" >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq RDE Redis" >nul 2>&1
timeout /t 2 /nobreak >nul
echo    OK
echo.

REM Backup do banco
echo [2/4] Fazendo backup do banco atual...
set "DB_FILE=rde_local.db"
if exist "%DB_FILE%" (
    copy "%DB_FILE%" "%DB_FILE%.backup_%DATE:/=%_%TIME::=%" >nul
    echo    Backup criado: %DB_FILE%.backup
)

REM Backup do WAL se existir
if exist "%DB_FILE%-wal" (
    copy "%DB_FILE%-wal" "%DB_FILE%-wal.backup" >nul
    echo    Backup do WAL criado.
)
echo.

REM Recuperacao
echo [3/4] Executando recuperacao...
python -c "
import sqlite3, os, sys

db = 'rde_local.db'

if not os.path.exists(db):
    print('    Banco nao encontrado. Nada a recuperar.')
    sys.exit(0)

# Tenta conectar e forcar checkpoint
try:
    conn = sqlite3.connect(db)
    conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    conn.execute('PRAGMA journal_mode=DELETE')
    conn.execute('PRAGMA synchronous=NORMAL')
    conn.execute('PRAGMA temp_store=MEMORY')
    
    # Verifica integridade
    cur = conn.execute('PRAGMA integrity_check')
    result = cur.fetchall()
    if all(row[0] == 'ok' for row in result):
        print('    Integridade: OK')
    else:
        print('    ERRO: Banco corrompido!')
        print('    ', result)
        conn.close()
        sys.exit(1)
    
    # Mostra estatisticas
    cur = conn.execute(\"SELECT COUNT(*) FROM users\")
    print(f'    Usuarios: {cur.fetchone()[0]}')
    
    cur = conn.execute(\"SELECT COUNT(*) FROM sqlite_master WHERE type='table'\")
    print(f'    Tabelas: {cur.fetchone()[0]}')
    
    conn.close()
    print('    Banco recuperado com sucesso!')
except Exception as e:
    print(f'    ERRO: {e}')
    sys.exit(1)
"
echo.

REM Limpeza dos WAL/SHM
echo [4/4] Limpando arquivos temporarios...
if exist "%DB_FILE%-wal" del "%DB_FILE%-wal" 2>nul
if exist "%DB_FILE%-shm" del "%DB_FILE%-shm" 2>nul
forfiles /p "%~dp0" /m "*.session" /c "cmd /c del @file" 2>nul
echo    OK
echo.

echo ============================================
echo  Recuperacao concluida!
echo  Execute start_rde_completo.bat para iniciar.
echo ============================================
echo.
pause
