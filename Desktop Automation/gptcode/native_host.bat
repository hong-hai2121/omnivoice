@echo off
rem Chrome starts this file for each "Cap nhat kich ban"; do not print anything here.
setlocal
set "PY=%~dp0..\..\venv\Scripts\python.exe"
if not exist "%PY%" set "PY=py"
"%PY%" -u "%~dp0chay_quet.py" --native %*
