@echo off
setlocal
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
echo Python 3를 찾을 수 없습니다. python.org에서 Python 3.10 이상을 설치하고 Add Python to PATH를 선택하세요.
pause
:end
endlocal
