@echo off
cd /d "%~dp0"
set "PY=%~dp0..\..\venv\Scripts\python.exe"
if not exist "%PY%" set "PY=py"
"%PY%" cai_bo_quet.py %*
pause
