@echo off
setlocal
cd /d "%~dp0"
py -3 fh6_gmeter_overlay.py --round
if errorlevel 1 (
  python fh6_gmeter_overlay.py --round
)
