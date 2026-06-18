@echo off
REM Auto-restarting launcher for the terminal dashboard, bound to all interfaces
REM so it is reachable over Tailscale. cd to the folder that CONTAINS the package.
cd /d "%~dp0..\.."
:loop
echo [%date% %time%] starting dashboard >> dashboard.out
python -m copytrader.dashboard --host 0.0.0.0 >> dashboard.out 2>&1
echo [%date% %time%] dashboard exited, restarting in 5s >> dashboard.out
timeout /t 5 /nobreak >nul
goto loop
