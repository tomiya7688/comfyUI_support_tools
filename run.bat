@echo off
setlocal
cd /d "%~dp0"

rem Central GUI package root and UTF-8 console output.
set "PYTHONPATH=%~dp0"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

rem The GUI gets its own minimal environment. Backend launchers select their
rem own WebUI1111 / ComfyUI / Touka environments inside the application.
set "PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
    call "%~dp0setup_kadoka_tools.bat"
    if errorlevel 1 (
        echo.
        echo Tabbed Tools startup was cancelled because setup failed.
        pause
        exit /b 1
    )
)
if not exist "%PYTHON%" (
    echo.
    echo Tabbed Tools Python environment was not created: "%PYTHON%"
    pause
    exit /b 1
)

"%PYTHON%" "%~dp0tabbed_tools_gui.py" %*
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" (
    echo.
    echo Kadoka Tools GUI exited with code %EXIT_CODE%.
    pause
)
exit /b %EXIT_CODE%
