@echo off
chcp 65001 >nul
title TikTok - chi DO NUT (an toan, khong bam gi)
cd /d "%~dp0"
echo.
echo   CHE DO AN TOAN: chi mo trang tai len cua TikTok, chup man hinh
echo   roi khoanh nut "Chon video" ma may nhin thay. KHONG bam, KHONG nap video.
echo.
echo   Xem ket qua o:  anh_thu\tiktok_b1_do_nut.png
echo     - khung DO day  = nut may se bam
echo     - khung XANH    = ung vien bi loai
echo.
"%~dp0..\venv\Scripts\python.exe" -X utf8 "%~dp0tiktok_chon_video.py" --chi-do %*
echo.
pause
