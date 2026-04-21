@echo off
REM =====================================================
REM WhisperKey main process restart script
REM Called from Config.exe on save
REM =====================================================

REM Kill main process
taskkill /F /IM WhisperKey.exe >nul 2>&1

REM Wait for process termination (also allows Mutex release)
timeout /t 2 /nobreak >nul

REM Launch main exe from the same directory as this batch
start "" "%~dp0WhisperKey.exe"

exit
