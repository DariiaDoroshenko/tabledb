@echo off
cd /d "%~dp0"
set PY=python
where py >nul 2>nul && set PY=py
start "" http://127.0.0.1:8765/
echo Web server is running on http://127.0.0.1:8765/ . Close this window to stop it.
%PY% run_server.py --port 8765
pause
