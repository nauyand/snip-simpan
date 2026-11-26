@echo off
rem Menjalankan SnipSimpan tanpa jendela konsol
cd /d "%~dp0"
where pyw >nul 2>nul && (start "" pyw snipsimpan.py & exit /b)
where pythonw >nul 2>nul && (start "" pythonw snipsimpan.py & exit /b)
echo Python belum terpasang. Unduh dari https://www.python.org/downloads/
pause
