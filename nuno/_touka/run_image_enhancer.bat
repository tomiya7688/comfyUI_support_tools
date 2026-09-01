@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "VENV_DIR=%~dp0.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
set "REQ_FILE=%~dp0requirements.txt"
set "INSTALL_REQUIRED=0"

if not exist "%VENV_PY%" (
  echo Creating the local Python environment in .venv ...
  py -3.10 -m venv "%VENV_DIR%" >nul 2>&1
  if errorlevel 1 python -m venv "%VENV_DIR%" >nul 2>&1
  if not exist "%VENV_PY%" (
    echo Could not create the local .venv.
    echo Install Python 3.10 or newer, then run this file again.
    pause
    exit /b 1
  )
  set "INSTALL_REQUIRED=1"
)

if "%INSTALL_REQUIRED%"=="0" (
  "%VENV_PY%" -c "import numpy, PIL; assert numpy.__version__ == '1.26.4' and PIL.__version__ == '10.4.0'" >nul 2>&1
  if errorlevel 1 set "INSTALL_REQUIRED=1"
)

if "%INSTALL_REQUIRED%"=="1" (
  echo Installing the pinned Pillow and NumPy versions ...
  "%VENV_PY%" -m pip install --disable-pip-version-check --upgrade pip >nul 2>&1
  "%VENV_PY%" -m pip install --disable-pip-version-check --no-input --only-binary=:all: -r "%REQ_FILE%"
  if errorlevel 1 (
    echo Dependency installation failed. Check your internet connection and run this file again.
    pause
    exit /b 1
  )
)

"%VENV_PY%" "%~dp0image_enhancer.py"
set "EXIT_CODE=%ERRORLEVEL%"
endlocal & exit /b %EXIT_CODE%
