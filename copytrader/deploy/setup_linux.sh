#!/usr/bin/env bash
# One-shot installer: run the copy-trader (PAPER) as an always-on systemd service.
# Works on Oracle Cloud Always Free (Ubuntu or Oracle Linux), or any Linux VM/VPS.
# Usage:  bash copytrader/deploy/setup_linux.sh
set -euo pipefail

# folder that CONTAINS the copytrader package (two levels up from this script)
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
USER_NAME="$(whoami)"
PORT="${PORT:-8787}"

echo ">> project root : $ROOT"
echo ">> service user : $USER_NAME"
echo ">> dashboard port: $PORT"

# --- python + deps (apt for Ubuntu/Debian, dnf for Oracle Linux/RHEL) ---
if command -v apt-get >/dev/null; then
  sudo apt-get update -y
  sudo apt-get install -y python3 python3-pip
elif command -v dnf >/dev/null; then
  sudo dnf install -y python3 python3-pip
fi
python3 -m pip install --user --quiet requests || sudo python3 -m pip install --quiet requests

# --- systemd service (auto-start on boot, auto-restart on crash) ---
sudo tee /etc/systemd/system/copytrader.service >/dev/null <<EOF
[Unit]
Description=Polymarket copy-trader (paper engine + dashboard)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER_NAME
WorkingDirectory=$ROOT
Environment=PORT=$PORT
ExecStart=/usr/bin/python3 -m copytrader.serve
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now copytrader

# --- open the port on the VM's local firewall (Oracle's cloud security list is separate) ---
if command -v ufw >/dev/null && sudo ufw status | grep -q active; then
  sudo ufw allow "${PORT}/tcp" || true
fi
sudo iptables -I INPUT -p tcp --dport "$PORT" -j ACCEPT 2>/dev/null || true

echo
echo ">> done. status:"
sudo systemctl status copytrader --no-pager -l | head -n 12 || true
echo
echo ">> dashboard: http://<this-vm-public-ip>:$PORT   (also open ingress $PORT in the Oracle console)"
