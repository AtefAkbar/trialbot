# One-shot deploy for the copy-trader PAPER bot on an always-on Windows laptop.
# Run in an ADMINISTRATOR PowerShell, from anywhere:
#   powershell -ExecutionPolicy Bypass -File C:\copytrader-bot\copytrader\deploy\setup_windows.ps1
#
# It installs deps, stops the laptop sleeping, opens the dashboard port, and
# registers + starts auto-restarting engine/dashboard services. Paper only.

$ErrorActionPreference = "Stop"
$deploy = $PSScriptRoot                          # ...\copytrader\deploy
$root   = (Resolve-Path "$deploy\..\..").Path    # folder that CONTAINS the copytrader package

Write-Host "[1/4] Installing Python deps (requests)..."
python -m pip install --quiet requests

Write-Host "[2/4] Disabling sleep on AC power (keep it plugged in)..."
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
powercfg /change monitor-timeout-ac 0
powercfg /setacvalueindex SCHEME_CURRENT SUB_BUTTONS LIDACTION 0   # lid close = do nothing
powercfg /S SCHEME_CURRENT

Write-Host "[3/4] Opening firewall TCP 8787 for the dashboard..."
netsh advfirewall firewall delete rule name="CopyTrader Dashboard" 2>$null | Out-Null
netsh advfirewall firewall add rule name="CopyTrader Dashboard" dir=in action=allow protocol=TCP localport=8787 | Out-Null

Write-Host "[4/4] Registering + starting auto-restart services..."
schtasks /Create /TN "CopyTraderEngine"    /TR "`"$deploy\run_engine.bat`""    /SC ONLOGON /RL HIGHEST /F | Out-Null
schtasks /Create /TN "CopyTraderDashboard" /TR "`"$deploy\run_dashboard.bat`"" /SC ONLOGON /RL HIGHEST /F | Out-Null
schtasks /Run /TN "CopyTraderEngine"    | Out-Null
schtasks /Run /TN "CopyTraderDashboard" | Out-Null

$ip = (tailscale ip -4 2>$null | Select-Object -First 1)
Write-Host ""
Write-Host "DONE — engine + dashboard are running and will auto-start at every logon."
Write-Host "Working dir: $root"
if ($ip) {
  Write-Host "Open the terminal from any tailnet device:  http://$($ip):8787"
} else {
  Write-Host "Install + sign into Tailscale, then browse:  http://<this-pc-name>:8787"
}
Write-Host "Tip: enable auto-login via 'netplwiz' so it starts on boot before you log in."
