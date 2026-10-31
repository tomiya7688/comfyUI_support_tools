@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "VENV_DIR=%~dp0.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
set "LEGACY_VENV=%~dp0.venv-python-pre-31118"
set "REQ_FILE=%~dp0requirements.txt"
set "INSTALL_REQUIRED=0"
set "PYTHON31118=%KADOKA_PYTHON31118%"
set "PYTHON_LAUNCHER="

if not exist "%VENV_PY%" goto create_environment

:validate_environment
"%VENV_PY%" -c "import sys; raise SystemExit(0 if sys.implementation.name == 'cpython' and sys.version_info >= (3, 11, 18) and sys.version_info < (3, 13) else 1)" >nul 2>&1
if errorlevel 1 goto migrate_unsupported_environment
goto check_dependencies

:create_environment
call :verify_creation_python
if errorlevel 1 goto python_not_found
echo Creating the local Python 3.11.18 environment in .venv ...
if defined PYTHON31118 goto create_with_configured_python
%PYTHON_LAUNCHER% -m venv "%VENV_DIR%"
if errorlevel 1 goto creation_failed
goto validate_environment

:create_with_configured_python
"%PYTHON31118%" -m venv "%VENV_DIR%"
if errorlevel 1 goto creation_failed
goto validate_environment

:check_dependencies
"%VENV_PY%" -c "import numpy, PIL; assert numpy.__version__ == '1.26.4' and PIL.__version__ == '10.4.0'" >nul 2>&1
if errorlevel 1 set "INSTALL_REQUIRED=1"
"%VENV_PY%" -c "import certifi; assert tuple(map(int, certifi.__version__.split('.'))) >= (2026, 10, 19)" >nul 2>&1
if errorlevel 1 set "INSTALL_REQUIRED=1"
"%VENV_PY%" -c "import pip; assert tuple(map(int, pip.__version__.split('.'))) >= (26, 2, 2)" >nul 2>&1
if errorlevel 1 set "INSTALL_REQUIRED=1"

if "%INSTALL_REQUIRED%"=="1" goto install_dependencies
goto configure_pip_trust

:install_dependencies
echo Installing the pinned Pillow and NumPy versions ...
REM Upgrade the bootstrap installer from its SHA-256 pinned Python.org wheel.
call :configure_bootstrap_trust
if errorlevel 1 goto setup_failed
"%VENV_PY%" -m pip install --disable-pip-version-check "pip @ https://files.pythonhosted.org/packages/3f/06/3e4420302363fbb71be3c7f35ce042f54bfca330e3e66b3a2e3c4cca579f/pip-26.2.2-py3-none-any.whl#sha256=fd7f4dfa8190e014013b9f08f3e973f4e4c26ffd179a204895533a7254813a70"
if errorlevel 1 goto setup_failed
"%VENV_PY%" -m pip config --site set global.use-deprecated legacy-certs
if errorlevel 1 goto setup_failed
"%VENV_PY%" -m pip install --disable-pip-version-check --no-input --only-binary=:all: -r "%REQ_FILE%"
if errorlevel 1 (
  echo Dependency installation failed. Check your internet connection and run this file again.
  pause
  exit /b 1
)
goto verify_ca_bundle

:configure_pip_trust
"%VENV_PY%" -m pip config --site set global.use-deprecated legacy-certs
if errorlevel 1 goto setup_failed
goto verify_ca_bundle

:verify_ca_bundle
"%VENV_PY%" "%~dp0..\..\tools\security\check_python_ca.py"
if errorlevel 1 goto setup_failed
goto launch_application

:configure_bootstrap_trust
"%VENV_PY%" -c "import pip; raise SystemExit(0 if tuple(map(int, pip.__version__.split('.')[:2])) >= (24, 2) else 1)" >nul 2>&1
if errorlevel 1 exit /b 0
"%VENV_PY%" -m pip config --site set global.use-deprecated legacy-certs
exit /b %ERRORLEVEL%

:launch_application
"%VENV_PY%" "%~dp0image_enhancer.py"
set "EXIT_CODE=%ERRORLEVEL%"
endlocal & exit /b %EXIT_CODE%

:migrate_unsupported_environment
echo The existing .venv is not CPython 3.11.18 through 3.12.
if exist "%LEGACY_VENV%" goto backup_already_exists
call :verify_creation_python
if errorlevel 1 goto python_not_found
move "%VENV_DIR%" "%LEGACY_VENV%" >nul
if errorlevel 1 goto setup_failed
echo The previous environment was preserved at "%LEGACY_VENV%".
goto create_environment

:backup_already_exists
echo The backup path "%LEGACY_VENV%" already exists; no environment was moved.
exit /b 1

:creation_failed
echo Could not create the supported .venv.
if not exist "%LEGACY_VENV%" goto setup_failed
if not exist "%VENV_DIR%" goto restore_previous_environment
if exist "%VENV_DIR%.failed" goto restore_failed_environment_blocked
move "%VENV_DIR%" "%VENV_DIR%.failed" >nul
if errorlevel 1 goto restore_failed_environment_blocked

:restore_previous_environment
move "%LEGACY_VENV%" "%VENV_DIR%" >nul
if errorlevel 1 goto restore_failed_environment_blocked
echo Restored the previous .venv. The failed new environment, if any, was preserved with a .failed suffix.
goto setup_failed

:restore_failed_environment_blocked
echo The previous environment is preserved at "%LEGACY_VENV%".
echo Restore it manually after moving any incomplete .venv out of the way.
goto setup_failed

:python_not_found
echo CPython 3.11.18 through 3.12 was not found. Set KADOKA_PYTHON31118 to a compatible python.exe or install it with the py launcher.
exit /b 1

:setup_failed
echo Failed to prepare the local Python environment.
if exist "%LEGACY_VENV%" echo The previous environment remains at "%LEGACY_VENV%".
exit /b 1

:verify_creation_python
if defined PYTHON31118 goto verify_configured_python
where py >nul 2>nul
if errorlevel 1 exit /b 1
set "PYTHON_LAUNCHER=py -3.12"
%PYTHON_LAUNCHER% -c "import sys; raise SystemExit(0 if sys.implementation.name == 'cpython' and sys.version_info >= (3, 11, 18) and sys.version_info < (3, 13) else 1)" >nul 2>&1
if not errorlevel 1 exit /b 0
set "PYTHON_LAUNCHER=py -3.11"
%PYTHON_LAUNCHER% -c "import sys; raise SystemExit(0 if sys.implementation.name == 'cpython' and sys.version_info >= (3, 11, 18) and sys.version_info < (3, 13) else 1)" >nul 2>&1
if errorlevel 1 exit /b 1
exit /b 0

:verify_configured_python
if not exist "%PYTHON31118%" exit /b 1
"%PYTHON31118%" -c "import sys; raise SystemExit(0 if sys.implementation.name == 'cpython' and sys.version_info >= (3, 11, 18) and sys.version_info < (3, 13) else 1)" >nul 2>&1
if errorlevel 1 exit /b 1
exit /b 0
