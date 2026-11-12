@echo off
rem Starts JARVIS (orb + voice + panel) without a console window. Only one can run at a time.
cd /d "%~dp0"
start "" "%~dp0.venv\Scripts\pythonw.exe" -m jarvis %*
