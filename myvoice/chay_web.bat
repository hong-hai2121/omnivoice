@echo off
chcp 65001 >nul
title myvoice - bang dieu khien web
cd /d "%~dp0.."
echo Dang khoi dong bang dieu khien web...
echo (Dong cua so nay la tat server.)
echo.
"%~dp0..\venv\Scripts\python.exe" -m myvoice.web.server
pause
