@echo off
cd /d "%~dp0"
py -m pip install --quiet pygame-ce
py game.py
if errorlevel 1 pause
