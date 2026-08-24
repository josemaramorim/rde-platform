@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo  RDE - Corrigir Admin / Banco
echo ============================================
echo.
echo Parando backend na porta 8000...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000" ^| findstr "LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
)
timeout /t 2 /nobreak >nul

echo Criando/recuperando admin...
set PYTHONPATH=F:\RDE
python -m src.corrigir_admin
if errorlevel 1 (
    echo.
    echo ERRO na correcao. Tente manualmente:
    echo   python -m src.create_admin
) else (
    echo.
    echo Corrigido! Inicie o backend: start_backend.bat
)
echo.
pause
