@echo off
setlocal
cd /d "%~dp0"

rem Keep CMD-parsed setup ASCII-only. Python itself runs with UTF-8 enabled.
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "VENV_DIR=%~dp0.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
set "LEGACY_VENV=%~dp0.venv-python-pre-31118"
set "REQUIREMENTS=%~dp0requirements-kadoka-tools.txt"
set "PYTHON31118=%KADOKA_PYTHON31118%"
set "PYTHON_LAUNCHER="

if exist "%VENV_PY%" goto validate_environment
goto create_environment

:create_environment
call :verify_creation_python
if errorlevel 1 goto python_not_found
echo Creating the Tabbed Tools Python 3.11.18 environment...
if defined PYTHON31118 goto create_with_configured_python
%PYTHON_LAUNCHER% -m venv "%VENV_DIR%"
if errorlevel 1 goto creation_failed
goto validate_environment

:create_with_configured_python
"%PYTHON31118%" -m venv "%VENV_DIR%"
if errorlevel 1 goto creation_failed
goto validate_environment

:validate_environment
"%VENV_PY%" -c "import sys; raise SystemExit(0 if sys.implementation.name == 'cpython' and sys.version_info >= (3, 11, 18) and sys.version_info < (3, 13) else 1)"
if errorlevel 1 goto migrate_unsupported_environment

:install_requirements
echo Checking Tabbed Tools dependencies...
REM Pin the bootstrap installer to avoid inheriting an unverified seeded bundle.
call :configure_bootstrap_trust
if errorlevel 1 goto setup_failed
"%VENV_PY%" -m pip install --disable-pip-version-check "pip @ https://files.pythonhosted.org/packages/3f/06/3e4420302363fbb71be3c7f35ce042f54bfca330e3e66b3a2e3c4cca579f/pip-26.2.2-py3-none-any.whl#sha256=fd7f4dfa8190e014013b9f08f3e973f4e4c26ffd179a204895533a7254813a70"
if errorlevel 1 goto setup_failed

"%VENV_PY%" -m pip config --site set global.use-deprecated legacy-certs
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
echo Use CPython 3.11.18 through 3.12 with venv and pip, then run this file again.
if exist "%LEGACY_VENV%" echo The previous .venv remains at "%LEGACY_VENV%".
exit /b 1

:python_not_found
echo Python launcher not found. Set KADOKA_PYTHON31118 to the supported python.exe path.
exit /b 1

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

:verify_creation_python
if defined PYTHON31118 goto verify_configured_python
where py >nul 2>nul
if errorlevel 1 exit /b 1
set "PYTHON_LAUNCHER=py -3.12"
%PYTHON_LAUNCHER% -c "import sys; raise SystemExit(0 if sys.implementation.name == 'cpython' and sys.version_info >= (3, 11, 18) and sys.version_info < (3, 13) else 1)" >nul 2>nul
if not errorlevel 1 exit /b 0
set "PYTHON_LAUNCHER=py -3.11"
%PYTHON_LAUNCHER% -c "import sys; raise SystemExit(0 if sys.implementation.name == 'cpython' and sys.version_info >= (3, 11, 18) and sys.version_info < (3, 13) else 1)" >nul 2>nul
if errorlevel 1 exit /b 1
exit /b 0

:configure_bootstrap_trust
"%VENV_PY%" -c "import pip; raise SystemExit(0 if tuple(map(int, pip.__version__.split('.')[:2])) >= (24, 2) else 1)" >nul 2>nul
if errorlevel 1 exit /b 0
"%VENV_PY%" -m pip config --site set global.use-deprecated legacy-certs
exit /b %ERRORLEVEL%

:verify_configured_python
"%PYTHON31118%" -c "import sys; raise SystemExit(0 if sys.implementation.name == 'cpython' and sys.version_info >= (3, 11, 18) and sys.version_info < (3, 13) else 1)" >nul 2>nul
if errorlevel 1 exit /b 1
exit /b 0
