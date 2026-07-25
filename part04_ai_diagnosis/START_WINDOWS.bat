@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 app.py
  goto :end
)
where python >nul 2>nul
if %errorlevel%==0 (
  python app.py
  goto :end
)
echo Python 3가 필요합니다. python.org에서 설치한 뒤 다시 실행하세요.
pause
:end
