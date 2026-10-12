@echo off
cd /d "%~dp0"
set PY=python
where py >nul 2>nul && set PY=py
%PY% run_tests.py -v
pause
