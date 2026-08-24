@echo off
cd /d C:\rde-frontend
set NODE_ENV=production
npm run build > NUL 2>&1
start "" /min cmd /c "npm run start >> F:\RDE\frontend.log 2>> F:\RDE\frontend_err.log"
