@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "ROOT_DIR=%%~fI"
set "PAYLOAD_DIR=%ROOT_DIR%\payload"
set "TARGET_APP=%~1"
if not defined TARGET_APP set "TARGET_APP=%LOCALAPPDATA%\Programs\Cursor\resources\app"
if not exist "%TARGET_APP%" if exist "%USERPROFILE%\AppData\Local\Programs\Cursor\resources\app" set "TARGET_APP=%USERPROFILE%\AppData\Local\Programs\Cursor\resources\app"
if not exist "%TARGET_APP%" (
  echo [install-local-patch] Cursor app resources directory not found: "%TARGET_APP%"
  echo Usage: Windows\安装.bat "C:\Users\^<You^>\AppData\Local\Programs\Cursor\resources\app"
  exit /b 2
)
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
%PYTHON_BIN%  -m cursor_zh apply --manifest "%PAYLOAD_DIR%\patch_manifest.json" --cursor-app "%TARGET_APP%" --enable-dynamic-market
set EXIT_CODE=%ERRORLEVEL%
if not "%EXIT_CODE%"=="0" pause
exit /b %EXIT_CODE%
