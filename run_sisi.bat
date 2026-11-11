@echo off
rem Сісі з вікном (без консолі). Консольна версія: run_sisi_console.bat
cd /d "%~dp0"
start "" ".venv\Scripts\pythonw.exe" -m sisi.gui
