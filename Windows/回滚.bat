@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "ROOT_DIR=%%~fI"
set "PAYLOAD_DIR=%ROOT_DIR%\payload"
set "PYTHONPATH=%PAYLOAD_DIR%;%PYTHONPATH%"
set "PYTHON_BIN="
where py >nul 2>nul && set "PYTHON_BIN=py -3"
if not defined PYTHON_BIN (
  where python >nul 2>nul && set "PYTHON_BIN=python"
)
if not defined PYTHON_BIN (
  where python3 >nul 2>nul && set "PYTHON_BIN=python3"
)
if not defined PYTHON_BIN (
  echo [cursor-zh] Python 3 not found. Please install Python 3 first.
  exit /b 3
)
%PYTHON_BIN%  -m cursor_zh rollback --state "%PAYLOAD_DIR%\.cursor_zh_state\last_apply.json"
set EXIT_CODE=%ERRORLEVEL%
if not "%EXIT_CODE%"=="0" pause
exit /b %EXIT_CODE%
