@echo off
rem Memasang PySide6 dan segno (cukup sekali)
cd /d "%~dp0"
where py >nul 2>nul && (py -m pip install -r requirements.txt) || (python -m pip install -r requirements.txt)
pause
