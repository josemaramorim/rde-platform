@echo off
title RDE Platform - Cliente
cd /d "%~dp0"

echo ====================================
echo   RDE Platform - Modo Cliente
echo ====================================
echo.
echo Se for a primeira execucao, abra o navegador em:
echo   http://localhost:8000/setup
echo para configurar o servidor do administrador.
echo.
echo Limpando processos anteriores na porta 8000...

REM 1) Mata todos os processos rde-server.exe (pelo nome)
taskkill /f /im "rde-server.exe" >nul 2>&1
echo  Processos rde-server finalizados.

REM 2) Mata qualquer outro processo segurando a porta 8000
setlocal enabledelayedexpansion
set "pid="
for /f "tokens=*" %%a in ('netstat -ano ^| findstr /C:":8000"') do (
    set "linha=%%a"
    for %%b in (!linha!) do set "pid=%%b"
    if not "!pid!"=="" (
        echo  Matando processo !pid! na porta 8000...
        taskkill /f /pid !pid! >nul 2>&1
    )
)
endlocal

REM 3) Aguarda liberacao da porta
echo  Aguardando liberacao...
timeout /t 5 /nobreak >nul

echo.
echo Iniciando servidor local...
echo.
start /B /MIN "" "rde-server\rde-server.exe"
timeout /t 4 /nobreak >nul
start http://localhost:8000/setup

echo Servidor rodando em http://localhost:8000/setup
echo.
echo Pressione ENTER para parar o servidor.
pause >nul

taskkill /f /im "rde-server.exe" >nul 2>&1
echo Servidor encerrado.
