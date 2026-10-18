@echo off
REM ============================================================
REM  Build script for mc-server-panel
REM  Requires: pip install -r requirements-dev.txt
REM  Output:
REM    dist\MCPanel.exe              单文件版（自用/做安装包用）
REM    dist\MCPanel-Setup.exe        安装包（内嵌单文件版）
REM    dist\MCPanel-portable\        免安装目录版（发布 Release 用，符合 LGPL 可替换要求）
REM ============================================================
setlocal
cd /d "%~dp0"

set "DATA=--add-data assets\icon.ico;. --add-data assets\check.svg;. --add-data assets\arrow_up.svg;. --add-data assets\arrow_down.svg;."
set "ICON=--icon assets\icon.ico"

echo.
echo [1/3] onefile : dist\MCPanel.exe
python -m PyInstaller --noconfirm --clean --onefile --windowed %ICON% --name MCPanel ^
  %DATA% --distpath dist --workpath build app.py
if errorlevel 1 goto :err

echo.
echo [2/3] installer : dist\MCPanel-Setup.exe
python -m PyInstaller --noconfirm --clean --onefile --windowed %ICON% --name MCPanel-Setup ^
  --add-data "dist\MCPanel.exe;payload" --distpath dist --workpath build setup.py
if errorlevel 1 goto :err

echo.
echo [3/3] portable dir : dist\MCPanel-portable\
python -m PyInstaller --noconfirm --clean --onedir --windowed %ICON% --name MCPanel-portable ^
  %DATA% --distpath dist --workpath build app.py
if errorlevel 1 goto :err

echo.
echo Done. Output in .\dist
exit /b 0

:err
echo.
echo BUILD FAILED
pause
exit /b 1
