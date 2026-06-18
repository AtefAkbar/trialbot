# Deploy the copy-trader on an always-on Windows laptop (via Tailscale)

Runs the paper engine + dashboard 24/7 on an old Windows laptop, reachable from
your other devices over Tailscale. Read-only paper bot — no live orders.

Assume the package lives at `C:\copytrader-bot\copytrader\` (so the folder that
*contains* the package is `C:\copytrader-bot`). Adjust paths if you put it elsewhere.

---

## 1. Install Python + Tailscale (on the Windows laptop)
- Python 3: https://python.org/downloads — **check "Add python.exe to PATH"** during install.
- Tailscale: https://tailscale.com/download/windows — sign in with the **same account** as your Mac.
- Verify in PowerShell:
  ```powershell
  python --version
  tailscale ip -4        # note this 100.x.y.z address
  ```

## 2. Get the code onto the laptop
Easiest once both machines are on Tailscale — use Taildrop. **On your Mac:**
```bash
cd "/Users/smatefakbar/Claude project tradaing"
zip -r copytrader.zip copytrader -x '*/__pycache__/*' '*/state.json' '*.out' '*.log'
tailscale file cp copytrader.zip <windows-machine-name>:
```
**On Windows:** receive it, then unzip to `C:\copytrader-bot\`:
```powershell
mkdir C:\copytrader-bot
cd C:\copytrader-bot
tailscale file get .
Expand-Archive .\copytrader.zip -DestinationPath .
python -m pip install requests
```

## 3. Stop the laptop from sleeping (PowerShell as Administrator)
```powershell
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
powercfg /change monitor-timeout-ac 0
REM do nothing when the lid closes (so it runs lid-closed on AC power):
powercfg /setacvalueindex SCHEME_CURRENT SUB_BUTTONS LIDACTION 0
powercfg /S SCHEME_CURRENT
```
Keep it **plugged into power**.

## 4. Allow the dashboard port through the firewall (Administrator)
```powershell
netsh advfirewall firewall add rule name="CopyTrader Dashboard" dir=in action=allow protocol=TCP localport=8787
```

## 5. Auto-start engine + dashboard at logon
The two `.bat` launchers in `copytrader\deploy\` auto-restart on crash. Register them:
```powershell
schtasks /Create /TN "CopyTraderEngine"    /TR "C:\copytrader-bot\copytrader\deploy\run_engine.bat"    /SC ONLOGON /F
schtasks /Create /TN "CopyTraderDashboard" /TR "C:\copytrader-bot\copytrader\deploy\run_dashboard.bat" /SC ONLOGON /F
```
Then either reboot, or start them now without waiting for a logon:
```powershell
schtasks /Run /TN "CopyTraderEngine"
schtasks /Run /TN "CopyTraderDashboard"
```
> For "runs even before anyone logs in," enable Windows auto-login (`netplwiz`) so
> ONLOGON fires on boot — simplest reliable option for a home server.

## 6. Access it from anywhere on your tailnet
From your Mac/phone (Tailscale running), open:
```
http://<windows-machine-name>:8787      (MagicDNS)   — or —
http://100.x.y.z:8787                    (the tailscale ip from step 1)
```

## Notes
- **Tighter security:** `--host 0.0.0.0` (in run_dashboard.bat) exposes 8787 on every
  interface including local Wi-Fi. To restrict to Tailscale only, edit the bat to
  `--host 100.x.y.z` (your tailscale ip). It's a read-only paper dashboard, so 0.0.0.0
  on a home network is low risk, but the tailscale-ip bind is cleanest.
- **Check status remotely:** `python -m copytrader.report` on the Windows box, or just
  watch the dashboard.
- **Move the daily 9am check-in** to this machine if you want it independent of your Mac
  (re-create the scheduled task here, or just rely on the dashboard).
- **Sleep still pauses everything** if Windows ever sleeps — step 3 prevents that on AC.
