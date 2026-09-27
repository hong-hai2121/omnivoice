@echo off
chcp 65001 >nul
title TikTok - CHUP TOAN TRANG soan bai (khong bam gi)
cd /d "%~dp0"
echo.
echo   AN TOAN TUYET DOI: chi cuon trang va chup anh. KHONG bam, KHONG go,
echo   KHONG dang. Cuon xong no tu keo tro lai len dau trang.
echo.
echo   Dung de day cho bot cho moi tren trang (cong tac "Dang theo lich",
echo   o ngay gio, nut Dang...). Truoc khi chay: mo san mot video o man
echo   soan bai cua TikTok Studio.
echo.
echo   Xem ket qua o:  anh_thu\khaosat_00.png, khaosat_01.png, ...
echo.
pause
"%~dp0..\venv\Scripts\python.exe" -X utf8 "%~dp0tiktok_khao_sat.py" %*
echo.
pause
