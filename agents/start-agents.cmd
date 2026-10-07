@echo off
rem Starts the DungeonTuber agents that are next to this script (dt-wiz-light.exe, dt-voxalyzer.exe, dt-youtube.exe), each in its own window.
rem
rem The agents read server, token and name from the agents.json next to them (Settings > Agents > Download agents.json), so no arguments are
rem needed. Arguments given here are passed on to every agent, e.g.:  start-agents.cmd --server https://music.example.com --token TOKEN
setlocal enabledelayedexpansion
set "HERE=%~dp0"
set STARTED=0
for %%A in (dt-wiz-light dt-voxalyzer dt-youtube) do (
  if exist "%HERE%%%A.exe" (
    start "DungeonTuber %%A" /D "%HERE%" cmd /k ""%HERE%%%A.exe" %*"
    set /a STARTED+=1
  ) else (
    echo Skipping %%A: %%A.exe is not next to this script
  )
)
echo Started !STARTED! agent^(s^).
