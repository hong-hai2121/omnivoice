@echo off
chcp 65001 >nul
title TikTok - NAP VIDEO that (khong bam Dang)
cd /d "%~dp0"
echo.
echo   Se mo trang tai len cua TikTok bang Chrome "Profile 83",
echo   bam ngam vao nut "Chon video", roi dat duong dan video vao
echo   hop thoai chon file. TikTok bat dau nap video len that.
echo.
echo   KHONG bam nut Dang, KHONG dien caption. Video chi nam o man
echo   soan bai, chua len kenh. Muon bo thi dong tab la xong.
echo.
echo   Con tro chuot cua ban KHONG bi dung toi. Cu lam viec binh thuong.
echo.
echo   Doi video khac:  chay_nap_video.bat --video "D:\duong\dan\video.mp4"
echo.
pause
"%~dp0..\venv\Scripts\python.exe" -X utf8 "%~dp0tiktok_chon_video.py" %*
echo.
pause
