@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 launcher.py
  goto :end
)
where python >nul 2>nul
if %errorlevel%==0 (
  python launcher.py
  goto :end
)
echo Python 3을 찾지 못했습니다. Python 3.10 이상을 설치하고 PATH에 추가한 뒤 다시 실행하세요.
pause
:end
endlocal
