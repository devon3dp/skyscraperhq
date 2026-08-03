@echo off
REM qsb_box_grind_run.cmd - box-side offline-first grind tick (Windows worker box).
REM Runs grind then rollup against the LOCAL Ollama only. Makes ZERO calls to
REM SkyscraperHQ, so it keeps producing work even when HQ is unreachable.
REM Registered as a Windows Scheduled Task (QSB_Offline_Grinder) so it fires on
REM the box's OWN timer, independent of HQ. Full python.exe path is required
REM (bare 'python' resolves to the WindowsApps stub and silently no-ops).
set PY="C:\Program Files\Python311\python.exe"
if not exist %PY% set PY="%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
set AGENT="%USERPROFILE%\.qsb\qsb_box_grind_agent.py"
%PY% %AGENT% grind  >> "%USERPROFILE%\.qsb\grind.log" 2>&1
%PY% %AGENT% rollup >> "%USERPROFILE%\.qsb\grind.log" 2>&1
