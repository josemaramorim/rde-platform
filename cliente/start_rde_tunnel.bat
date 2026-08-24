@echo off
title RDE Platform + Cloudflare Tunnel
cd /d "%~dp0"

echo ============================================
echo   RDE Platform + Cloudflare Tunnel
echo ============================================
echo.

echo Iniciando servidor RDE...
start /B /MIN "" "cliente\rde-server\rde-server.exe"
timeout /t 5 /nobreak >nul

echo Iniciando tunnel Cloudflare...
echo.
python start_tunnel.py
pause
