@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  py -3 -m venv .venv
  if errorlevel 1 goto fail
)
.venv\Scripts\python.exe -m pip install -r requirements.txt "pyinstaller>=6,<7"
if errorlevel 1 goto fail
.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onefile --windowed --name ESR3_CE --collect-all RsInstrument --collect-all pyvisa_py app.py
if errorlevel 1 goto fail
echo Built: dist\ESR3_CE.exe
pause
exit /b 0
:fail
echo Build failed. See messages above.
pause
exit /b 1
