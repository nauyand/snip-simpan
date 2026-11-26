@echo off
rem Membuat SnipSimpan.exe (hasil ada di folder dist\)
cd /d "%~dp0"
where py >nul 2>nul && (set PY=py) || (set PY=python)
%PY% -m pip install -r requirements.txt pyinstaller
%PY% buat_icon.py
%PY% -m PyInstaller --noconfirm --onefile --windowed --name SnipSimpan --icon snipsimpan.ico snipsimpan.py
echo.
echo Selesai. File: dist\SnipSimpan.exe
pause
