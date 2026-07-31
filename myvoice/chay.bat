@echo off
chcp 65001 >nul
title myvoice - bang dieu khien web
cd /d "%~dp0.."
echo.
echo   Dang khoi dong myvoice (ban WEB)...
echo   Trinh duyet se tu mo. Dong cua so nay la tat server.
echo.
"%~dp0..\venv\Scripts\python.exe" -m myvoice.web.server
echo.
echo   Server da dung.
pause
