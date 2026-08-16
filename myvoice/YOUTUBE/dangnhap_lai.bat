@echo off
chcp 65001 >nul
title Dang nhap lai YouTube (lay token moi)
"%~dp0..\..\venv\Scripts\python.exe" -u "%~dp0dangnhap_lai.py"
echo.
pause
