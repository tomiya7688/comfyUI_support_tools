@echo off
setlocal
cd /d "%~dp0\..\.."

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PYTHON_CMD=python"

where py >nul 2>nul
if not errorlevel 1 set "PYTHON_CMD=py -3.10"

echo Installing Kadoka Tools runtime dependencies...
%PYTHON_CMD% -m pip install --disable-pip-version-check -r requirements-kadoka-tools.txt
if errorlevel 1 goto build_failed

echo Installing PyInstaller...
%PYTHON_CMD% -m pip install --disable-pip-version-check -r tools\build\requirements.txt
if errorlevel 1 goto build_failed

echo Building KadokaTools one-dir distribution...
%PYTHON_CMD% tools\build\build_one_dir.py --smoke-test
if errorlevel 1 goto build_failed

echo.
echo Build completed: dist\KadokaTools\
exit /b 0

:build_failed
echo.
echo KadokaTools one-dir build failed.
exit /b 1
