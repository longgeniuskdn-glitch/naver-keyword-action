@echo off
setlocal
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Python 3가 필요합니다. https://www.python.org 에서 설치할 때 Add Python to PATH를 선택하세요.
  pause
  exit /b 1
)
start "" "http://127.0.0.1:8780"
python launcher.py --no-browser
endlocal
