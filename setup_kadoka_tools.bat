@echo off
setlocal
cd /d "%~dp0"

rem Keep CMD-parsed setup ASCII-only. Python itself runs with UTF-8 enabled.
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "VENV_DIR=%~dp0.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
set "REQUIREMENTS=%~dp0requirements-kadoka-tools.txt"

if exist "%VENV_PY%" goto install_requirements

echo Creating the Tabbed Tools Python 3.10 environment...
where py >nul 2>nul
if not errorlevel 1 (
    py -3.10 -m venv "%VENV_DIR%"
) else (
    python -m venv "%VENV_DIR%"
)
if errorlevel 1 goto setup_failed

:install_requirements
echo Checking Tabbed Tools dependencies...
"%VENV_PY%" -m pip install --disable-pip-version-check -r "%REQUIREMENTS%"
if errorlevel 1 goto setup_failed

echo.
echo Tabbed Tools environment is ready.
echo Backend environments are kept separate: WebUI1111, ComfyUI, and Touka.
exit /b 0

:setup_failed
echo.
echo Failed to prepare the Tabbed Tools environment.
echo Install Python 3.10 with venv and pip, then run this file again.
exit /b 1
