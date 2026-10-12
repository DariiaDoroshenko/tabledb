@echo off
cd /d "%~dp0"
set PY=python
where py >nul 2>nul && set PY=py
echo Server is running. Close this window or press Ctrl+C to stop it.
%PY% run_server.py --port 8765
pause
