@echo off
setlocal
cd /d "%~dp0\..\.."

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PYTHON_CMD=python"

where py >nul 2>nul
if not errorlevel 1 set "PYTHON_CMD=py -3.10"

echo Installing Kadoka Tools runtime dependencies...
REM Upgrade bootstrap pip via the SHA-256 URL published by Python.org.
%PYTHON_CMD% -m pip install --disable-pip-version-check "pip @ https://files.pythonhosted.org/packages/3f/06/3e4420302363fbb71be3c7f35ce042f54bfca330e3e66b3a2e3c4cca579f/pip-26.2.2-py3-none-any.whl#sha256=fd7f4dfa8190e014013b9f08f3e973f4e4c26ffd179a204895533a7254813a70"
if errorlevel 1 goto build_failed

%PYTHON_CMD% -m pip install --disable-pip-version-check "certifi>=2026.10.19"
if errorlevel 1 goto build_failed

%PYTHON_CMD% -m pip install --disable-pip-version-check -r requirements-kadoka-tools.txt
if errorlevel 1 goto build_failed

%PYTHON_CMD% tools\security\check_python_ca.py
if errorlevel 1 goto build_failed

echo Installing PyInstaller...
%PYTHON_CMD% -m pip install --disable-pip-version-check -r tools\build\requirements.txt
if errorlevel 1 goto build_failed

echo Building KadokaTools one-dir distribution...
%PYTHON_CMD% tools\build\build_one_dir.py --smoke-test
if errorlevel 1 goto build_failed

%PYTHON_CMD% tools\security\check_python_ca.py --distribution-root dist\KadokaTools
if errorlevel 1 goto build_failed

echo.
echo Build completed: dist\KadokaTools\
exit /b 0

:build_failed
echo.
echo KadokaTools one-dir build failed.
exit /b 1
