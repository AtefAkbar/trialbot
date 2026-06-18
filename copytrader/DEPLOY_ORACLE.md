# Deploy on Oracle Cloud Always Free (24/7, $0)

Runs the paper copy-trader on a free, always-on Oracle Cloud VM. Read-only paper
bot — no live orders.

## 1. Create the free VM
1. Sign up at https://www.oracle.com/cloud/free/ (needs a card for verification;
   Always Free resources are never charged).
2. Console → **Compute → Instances → Create Instance**.
3. Image & shape:
   - Image: **Canonical Ubuntu** (latest LTS).
   - Shape: **VM.Standard.E2.1.Micro** (AMD, 1 GB) — marked *Always Free*. (The ARM
     Ampere A1 is also free and bigger, but often "out of capacity"; the AMD micro
     is plenty for this bot.)
4. **Add your SSH key** (paste your `~/.ssh/id_*.pub`; create one with `ssh-keygen`
   if needed). Save the public IP shown after creation.

## 2. Open the dashboard port (Oracle security list)
Console → your VM's **subnet → Security List → Add Ingress Rule**:
- Source CIDR `0.0.0.0/0`, IP protocol **TCP**, destination port **8787**.
(Or skip this and use Tailscale instead — see Notes.)

## 3. Copy the code to the VM (from your Mac)
```bash
cd "/Users/smatefakbar/Claude project tradaing"
zip -r copytrader.zip copytrader -x '*/__pycache__/*' '*/state.json' '*.out' '*.log'
scp copytrader.zip ubuntu@<VM_PUBLIC_IP>:~/
```

## 4. Install + start the always-on service (on the VM)
```bash
ssh ubuntu@<VM_PUBLIC_IP>
sudo apt-get update -y && sudo apt-get install -y unzip
mkdir -p ~/copytrader-bot && unzip -o ~/copytrader.zip -d ~/copytrader-bot
bash ~/copytrader-bot/copytrader/deploy/setup_linux.sh
```
The script installs Python + `requests`, registers a **systemd service**
(`copytrader`) that auto-starts on boot and auto-restarts on crash, and starts it.

## 5. Use it
- Dashboard: `http://<VM_PUBLIC_IP>:8787`
- Status / logs / control on the VM:
  ```bash
  systemctl status copytrader
  journalctl -u copytrader -f         # live logs
  cd ~/copytrader-bot && python3 -m copytrader.report
  sudo systemctl restart copytrader   # restart
  sudo systemctl stop copytrader      # stop
  ```

## Notes
- **Truly 24/7:** a VM has no sleep and no function timeout — it just runs. systemd
  brings it back after reboots or crashes.
- **Keep the instance from being reclaimed:** Oracle may reclaim *idle* Always-Free
  VMs. Upgrading the account to "Pay As You Go" keeps Always-Free resources free
  **and** stops reclamation (you still pay $0 as long as you only use free shapes).
- **Tighter security (recommended):** instead of opening port 8787 to the world,
  install Tailscale on the VM (`curl -fsSL https://tailscale.com/install.sh | sh &&
  sudo tailscale up`) and bind the dashboard to the tailnet only — edit the service
  `Environment=PORT=8787` stays, but change `copytrader.serve` to bind your tailscale
  IP, or just reach `http://<vm-tailscale-ip>:8787` and keep the Oracle ingress closed.
- **State persistence:** `state.json` lives on the VM's disk, so it survives restarts
  (unlike ephemeral PaaS filesystems).
