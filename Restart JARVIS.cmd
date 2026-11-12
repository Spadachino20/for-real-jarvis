@echo off
rem Closes JARVIS if it is running (even if the orb froze or vanished) and starts it again.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process -Filter 'Name=''pythonw.exe''' | ? { $_.CommandLine -match '-m jarvis(\s|$)' } | %% { taskkill /PID $_.ProcessId /T /F | Out-Null }"
timeout /t 2 /nobreak >nul
call "%~dp0Start JARVIS.cmd"
