@echo off
rem Aura Phone Sync PC agent. Keeps the phone wallpaper and lighting effect up to date.
cd /d "%~dp0"
start "" pythonw aura_agent.py
