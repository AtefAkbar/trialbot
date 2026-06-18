@echo off
REM Auto-restarting launcher for the copy-trader paper engine.
REM cd to the folder that CONTAINS the copytrader package (two levels up from here).
cd /d "%~dp0..\.."
:loop
echo [%date% %time%] starting engine >> engine.out
python -m copytrader.run >> engine.out 2>&1
echo [%date% %time%] engine exited, restarting in 5s >> engine.out
timeout /t 5 /nobreak >nul
goto loop
