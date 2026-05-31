@echo off
cd /d "%~dp0app"
python -m opai worker run %*
