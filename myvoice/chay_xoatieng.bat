@echo off
rem Mo GUI "Xoa tieng & chuan hoa video" (videongang\video_xoatieng.py).
rem   - dung pythonw.exe de KHONG co cua so console den; ffmpeg/ffprobe con cung
rem     chay an (CREATE_NO_WINDOW) nen khong nhay cua so cmd nua (01/11/2026)
rem   - loi khoi dong (neu co): videongang\video_xoatieng_loi.log + hop thoai
chcp 65001 >nul
set "PYW=%~dp0..\venv\Scripts\pythonw.exe"
set "PY=%~dp0..\venv\Scripts\python.exe"
set "APP=%~dp0videongang\video_xoatieng.py"
cd /d "%~dp0"

if exist "%PYW%" (
    start "" "%PYW%" "%APP%"
    exit /b
)
if exist "%PY%" (
    start "" "%PY%" "%APP%"
    exit /b
)

echo.
echo   Khong thay python cua du an:
echo     %PY%
echo   Tao lai venv roi chay lai file nay.
echo.
pause
