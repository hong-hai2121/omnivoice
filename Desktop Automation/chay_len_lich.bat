@echo off
chcp 65001 >nul
title TikTok - HEN GIO DANG tren man soan bai dang mo
cd /d "%~dp0"
echo.
echo   Buoc 3 - chay tren cua so TikTok DANG MO SAN (da nap video + dien mo ta).
echo   May se: bat nut tron "Len lich" o muc Thoi diem dang, chon NGAY trong
echo   bang lich, chon GIO/PHUT tren banh xe hai cot.
echo.
echo   MAC DINH KHONG BAM NUT DANG - chi dat gio roi de day cho ban xem lai.
echo   Them --bam-dang thi may moi bam nut "Len lich": video SE TU LEN KENH.
echo.
echo   TikTok doi: hen sau it nhat 15 phut, trong vong 10 ngay, phut boi so 5.
echo.
echo   Vi du:
echo     chay_len_lich.bat --khi-nao "2026-09-23 20:30"
echo     chay_len_lich.bat --khi-nao "2026-09-23 20:30" --bam-dang
echo.
echo   Xem ket qua o:  anh_thu\tiktok_b3_len_lich.png
echo.
pause
"%~dp0..\venv\Scripts\python.exe" -X utf8 "%~dp0tiktok_len_lich.py" %*
echo.
pause
