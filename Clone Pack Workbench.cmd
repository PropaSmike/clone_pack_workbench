@echo off
setlocal
cd /d "%~dp0"
set "__COMPAT_LAYER=%__COMPAT_LAYER% HighDpiAware"
python clone_pack_gui %*
if errorlevel 1 pause
