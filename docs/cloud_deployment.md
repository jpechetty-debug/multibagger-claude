# Deploying IntradaySignals to the Cloud (Free)

This guide covers how to deploy your trading bot to the cloud effectively for free.

## Recommended: Oracle Cloud "Always Free" (Best Performance)
Oracle Cloud offers the most generous free tier, providing an **Ampere ARM instance with 4 OCPUs and 24GB RAM**, which is powerful enough to run your bot, database, and backtests simultaneously 24/7.

### Step 1: Create Instance
1.  Sign up for **Oracle Cloud Free Tier**.
2.  Navigate to **Compute -> Instances -> Create Instance**.
3.  **Image**: Canonical Ubuntu 22.04 or 24.04.
4.  **Shape**: Select **Ampere** (VM.Standard.A1.Flex). Set OCPUs to 4 and RAM to 24GB.
5.  **SSH Keys**: Download the Private Key (you will need this to login).
6.  Click **Create**.

### Step 2: Connect via SSH
Open your terminal (or PowerShell on Windows) and run:
```powershell
ssh -i "path\to\ssh-key.key" ubuntu@<YOUR_INSTANCE_IP>
```
*(Note: If permission error on key, go to properties -> security and remove other users)*

### Step 3: Setup Environment
Run the following commands on the server:

```bash
# Update System
sudo apt update && sudo apt upgrade -y

# Install Python & Pip
sudo apt install python3-pip python3-venv -y

# Clone your code (or upload via SFTP)
mkdir bot
cd bot
# You can use drag-and-drop SFTP (FileZilla) to upload your project folder here.
```

### Step 4: Install Dependencies
```bash
# Create Virtual Environment
python3 -m venv venv
source venv/bin/activate

# Install Requirements
pip install pandas pandas_ta yfinance apscheduler pyyaml tqdm scipy requests
```

### Step 5: Run as a Background Service
To keep the bot running 24/7 even if you close the terminal, use `systemd`.

1.  Create service file:
```bash
sudo nano /etc/systemd/system/tradingbot.service
```

2.  Paste the following (Edit paths as needed):
```ini
[Unit]
Description=IntradaySignals Trading Bot
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/bot
ExecStart=/home/ubuntu/bot/venv/bin/python /home/ubuntu/bot/run_live.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

3.  Start the Bot:
```bash
sudo systemctl daemon-reload
sudo systemctl enable tradingbot
sudo systemctl start tradingbot
```

### Step 6: Monitor
```bash
# Check Logs
sudo journalctl -u tradingbot -f
```

---

## Alternative: Google Cloud (GCP) E2-Micro
- **Pros**: Very reliable.
- **Cons**: Small specs (2 vCPUs, 1GB RAM) - might struggle with heavy backtests but fine for live trading.
- **Region**: Only free in `us-west1`, `us-central1`, `us-east1`.

Process is similar: Create **e2-micro** instance -> SSH -> Install Python -> Run `systemd`.

## Important Notes for Cloud
1.  **Timezone**: Servers are usually UTC. Your bot handles this via `pytz` (configured as Asia/Kolkata), so it should work fine.
2.  **YFinance**: If `yfinance` blocks the server IP, you might need to use a proxy or run the data fetcher locally and push signals to the server (more complex). Oracle usually works fine.
