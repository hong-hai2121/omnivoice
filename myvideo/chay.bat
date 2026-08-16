@echo off
rem Bat ban WEB cua myvideo (giong myvoice\chay.bat).
rem Mo CUA SO NHO (chay.py): server chay nen, san sang la TU MO trang web.
rem   - dung pythonw.exe de khong nhay cua so console nao ca
rem   - loi khoi dong (neu co) duoc ghi ra myvideo\chay_loi.log + hien hop thoai
chcp 65001 >nul
set "PYW=%~dp0..\venv\Scripts\pythonw.exe"
set "PY=%~dp0..\venv\Scripts\python.exe"
cd /d "%~dp0.."

if exist "%PYW%" (
    start "" "%PYW%" "%~dp0chay.py"
    exit /b
)
if exist "%PY%" (
    start "" "%PY%" "%~dp0chay.py"
    exit /b
)

echo.
echo   Khong thay python cua du an:
echo     %PY%
echo   Tao lai venv roi chay lai file nay.
echo.
pause
