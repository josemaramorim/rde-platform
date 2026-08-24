@echo off
powershell -WindowStyle Hidden -Command "Get-NetTCPConnection -LocalPort 8002 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"
powershell -WindowStyle Hidden -Command "Get-NetTCPConnection -LocalPort 3000 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"
powershell -WindowStyle Hidden -Command "Get-NetTCPConnection -LocalPort 80 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"
taskkill /f /im caddy.exe >nul 2>&1
echo RDE encerrado.
timeout /t 2 /nobreak >nul
