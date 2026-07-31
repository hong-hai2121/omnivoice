@echo off
chcp 65001 >nul
title myvoice - GUI Tkinter (ban cu)
cd /d "%~dp0.."
echo.
echo   Dang mo GUI Tkinter (ban cu).
echo   Cach dung hang ngay gio la ban WEB: chay.bat
echo.
"%~dp0..\venv\Scripts\python.exe" "%~dp0scripts\amain_taogiong_gui.py"
pause
