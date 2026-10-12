@echo off
cd /d "%~dp0"
set PY=python
where py >nul 2>nul && set PY=py
%PY% run_gui.py --server http://127.0.0.1:8765
if errorlevel 1 pause
