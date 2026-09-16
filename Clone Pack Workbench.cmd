@echo off
cd /d "%~dp0"
python clone_pack_gui %*
if errorlevel 1 pause
