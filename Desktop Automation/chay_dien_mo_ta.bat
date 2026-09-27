@echo off
chcp 65001 >nul
title TikTok - dien TIEU DE + HASHTAG vao man soan bai dang mo
cd /d "%~dp0"
echo.
echo   Buoc 2 - chay tren cua so TikTok DANG MO SAN (buoc 1 da nap video).
echo   May se: do o "Mo ta", bam ngam vao cuoi bai, xoa ten file TikTok tu dien,
echo   go tieu de, roi go tung hashtag - moi hashtag cho bang goi y hien ra
echo   xong moi an ENTER de no thanh hashtag that.
echo.
echo   KHONG bam nut Dang.
echo.
echo   Vi du:
echo     chay_dien_mo_ta.bat --tieu-de "Full o Mimi audio So 118" --hashtag "#truyenaudio #fyp"
echo.
echo   Xem ket qua o:  anh_thu\tiktok_b2_mo_ta.png
echo.
pause
"%~dp0..\venv\Scripts\python.exe" -X utf8 "%~dp0tiktok_dien_mo_ta.py" %*
echo.
pause
