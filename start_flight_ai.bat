@echo off
title Whisper Flight AI Tour Guide Launcher v5.0.4 (Corrected v2)

:: Startup banner
echo ======================================================
echo    Whisper Flight AI Tour Guide - Starting
echo ======================================================
echo.

:: --- Define paths ---

:: !! Path to your project files !!
set "PROJECT_DIR=C:\Projects\WhisperFlight_AI"

:: Path to your Python virtual environment (Verify this is correct)
set "VENV_DIR=C:\Users\Admin\AppData\Local\Programs\Python\Python311\Scripts\whisper_env"

:: Path to SimConnect SDK (Verify this is correct)
set "SDK_PATH=C:\MSFS 2024 SDK\SimConnect SDK\lib"

:: --- Set derived paths ---
set "PATH=%PATH%;%SDK_PATH%"
set "VENV_ACTIVATE=%VENV_DIR%\Scripts\activate.bat"
set "PYTHON_EXEC=%VENV_DIR%\Scripts\python.exe"
set "MAIN_SCRIPT=%PROJECT_DIR%\main.py"
set "REQUIREMENTS=%PROJECT_DIR%\requirements.txt"
set "LOGS_DIR=%PROJECT_DIR%\logs"

:: Check project script
if not exist "%MAIN_SCRIPT%" (
    echo [ERROR] Main script not found at "%MAIN_SCRIPT%". Check PROJECT_DIR.
    goto :error
)

:: Check virtual environment activation script
if not exist "%VENV_ACTIVATE%" (
    echo [ERROR] Virtual environment activation script not found at "%VENV_ACTIVATE%". Check VENV_DIR.
    goto :error
)

:: Activate virtual environment
echo [INFO] Activating virtual environment...
call "%VENV_ACTIVATE%"
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to activate virtual environment. Check path and try again.
    goto :error
)

:: *** Change directory to the project directory ***
echo [INFO] Changing working directory to "%PROJECT_DIR%"
cd /D "%PROJECT_DIR%"
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to change directory to "%PROJECT_DIR%". Check path.
    goto :error
)


:: Install requirements (now checks requirements.txt in the current, correct directory)
if exist "%REQUIREMENTS%" (
    echo [INFO] Installing dependencies from "%REQUIREMENTS%"...
    "%PYTHON_EXEC%" -m pip install -r "%REQUIREMENTS%" >nul 2>&1
    if %ERRORLEVEL% neq 0 (
        echo [WARNING] Failed to install some packages. Check requirements.txt and network connection. Continuing anyway...
    ) else (
        echo [INFO] Dependencies checked/installed successfully.
    )
) else (
    echo [WARNING] requirements.txt not found at "%REQUIREMENTS%". Skipping package installation.
)

:: Create logs directory (checks/creates in the current, correct directory)
if not exist "%LOGS_DIR%" (
    echo [INFO] Creating logs directory at "%LOGS_DIR%"...
    mkdir "%LOGS_DIR%"
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Failed to create logs directory. Check permissions.
        goto :error
    )
    echo [INFO] Created logs directory.
)

:: Launch application (runs main.py using the full path variable)
echo [INFO] Launching application: "%MAIN_SCRIPT%"...
"%PYTHON_EXEC%" "%MAIN_SCRIPT%"
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Application failed to start. Check logs in "%LOGS_DIR%" for details.
    goto :error
)

:end
echo.
echo [INFO] Whisper Flight AI Tour Guide has stopped running.
echo ======================================================
pause
exit /b 0

:error
echo.
echo [ERROR] Launch failed. See above for details.
echo ======================================================
pause
exit /b 1