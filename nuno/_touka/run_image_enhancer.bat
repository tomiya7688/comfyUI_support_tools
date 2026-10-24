@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "VENV_DIR=%~dp0.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
set "REQ_FILE=%~dp0requirements.txt"
set "INSTALL_REQUIRED=0"
set "PYTHON310=%KADOKA_PYTHON310%"

if not exist "%VENV_PY%" (
  echo Creating the local Python environment in .venv ...
  if exist "%PYTHON310%" ("%PYTHON310%" -m venv "%VENV_DIR%" >nul 2>&1) else (py -3.10 -m venv "%VENV_DIR%" >nul 2>&1)
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
  "%VENV_PY%" -c "import pip; assert tuple(map(int, pip.__version__.split('.'))) >= (26, 2, 2)" >nul 2>&1
  if errorlevel 1 set "INSTALL_REQUIRED=1"
)

if "%INSTALL_REQUIRED%"=="1" (
  echo Installing the pinned Pillow and NumPy versions ...
  REM Upgrade the bootstrap pip with the Python.org SHA-256 pinned wheel first.
  "%VENV_PY%" -m pip install --disable-pip-version-check "pip @ https://files.pythonhosted.org/packages/3f/06/3e4420302363fbb71be3c7f35ce042f54bfca330e3e66b3a2e3c4cca579f/pip-26.2.2-py3-none-any.whl#sha256=fd7f4dfa8190e014013b9f08f3e973f4e4c26ffd179a204895533a7254813a70"
  if errorlevel 1 exit /b 1
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
