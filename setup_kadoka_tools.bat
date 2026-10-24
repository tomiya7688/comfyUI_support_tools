@echo off
setlocal
cd /d "%~dp0"

rem Keep CMD-parsed setup ASCII-only. Python itself runs with UTF-8 enabled.
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "VENV_DIR=%~dp0.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
set "REQUIREMENTS=%~dp0requirements-kadoka-tools.txt"
set "PYTHON310=%KADOKA_PYTHON310%"

if exist "%VENV_PY%" goto install_requirements

echo Creating the Tabbed Tools Python 3.10 environment...
if exist "%PYTHON310%" (
    "%PYTHON310%" -m venv "%VENV_DIR%"
) else (
    where py >nul 2>nul
    if not errorlevel 1 (py -3.10 -m venv "%VENV_DIR%") else (python -m venv "%VENV_DIR%")
)
if errorlevel 1 goto setup_failed

:install_requirements
echo Checking Tabbed Tools dependencies...
REM Python 3.10 ensurepip can seed a CA bundle with the affected emSign root.
"%VENV_PY%" -m pip install --disable-pip-version-check "pip @ https://files.pythonhosted.org/packages/3f/06/3e4420302363fbb71be3c7f35ce042f54bfca330e3e66b3a2e3c4cca579f/pip-26.2.2-py3-none-any.whl#sha256=fd7f4dfa8190e014013b9f08f3e973f4e4c26ffd179a204895533a7254813a70"
if errorlevel 1 goto setup_failed

"%VENV_PY%" -m pip install --disable-pip-version-check -r "%REQUIREMENTS%"
if errorlevel 1 goto setup_failed

"%VENV_PY%" "%~dp0tools\security\check_python_ca.py"
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
