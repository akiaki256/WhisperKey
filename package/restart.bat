@echo off
REM =====================================================
REM WhisperKey main process restart utility
REM 
REM Purpose:
REM   Terminates and relaunches the WhisperKey main process.
REM   Used by any component that needs to restart WhisperKey.
REM 
REM Callers:
REM   - Config.exe: after saving settings
REM   - WhisperKey.exe: from tray menu "Restart"
REM =====================================================

REM Kill main process
taskkill /F /IM WhisperKey.exe >nul 2>&1

REM Wait for process termination (also allows Mutex release)
timeout /t 2 /nobreak >nul

REM Launch main exe from the same directory as this batch
start "" "%~dp0WhisperKey.exe"

exit
