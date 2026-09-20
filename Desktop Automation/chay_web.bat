@echo off
chcp 65001 >nul
title TikTok - bang dieu khien web
cd /d "%~dp0"
echo.
echo   Dang bat bang dieu khien TikTok...
echo   Dia chi: http://127.0.0.1:8770
echo   Trinh duyet se tu mo. Dong cua so nay la tat server.
echo.
"%~dp0..\venv\Scripts\python.exe" -X utf8 "%~dp0chay_web.py"
echo.
pause
