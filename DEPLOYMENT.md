# RetroFit EvaraFlow - Raspberry Pi Zero W Deployment Guide

**Repository:** https://github.com/aditya08deole/Flow-1.git
**Version:** 2.1 (Comprehensive System Stability Fix)
**Target Device:** Raspberry Pi Zero W
**OS:** Raspberry Pi OS (Bookworm or equivalent)

---

## Pre-Requisites (Already Done)

Before following this guide, ensure:
- ✅ Raspberry Pi OS is installed on 32GB+ SD card (via Pi Imager)
- ✅ SSH is enabled (via Pi Imager)
- ✅ WiFi credentials configured (via Pi Imager)
- ✅ RPi is connected to power and WiFi
- ✅ You can SSH into the device

---

## Step 1: SSH into Raspberry Pi

Find your RPi's IP address using your router, network scanner, or:
```bash
# On your PC (if available):
arp-scan --local  # Linux/Mac
ipconfig /all      # Windows (look for device name or hostname)
```

Then SSH in:
```bash
ssh pi@<RPI_IP_ADDRESS>
# Default password: raspberry
```

Example:
```bash
ssh pi@192.168.1.100
```

---

## Step 2: Navigate to Home Directory

```bash
cd ~
```

---

## Step 3: Create Working Directory (RetroFit)

```bash
mkdir -p ~/RetroFit
cd ~/RetroFit
```

Verify the directory was created:
```bash
pwd
# Output should show: /home/pi/RetroFit
```

---

## Step 4: Clone the Repository

```bash
git clone https://github.com/aditya08deole/Flow-1.git
cd Flow-1
```

Verify the repository contents:
```bash
ls -la
# You should see: config.py, main_service.py, install_pi.sh, update.sh, etc.
```

---

## Step 5: Run the Installer Script

The installer will:
- Update system packages
- Install Python3 venv and dependencies
- Disable WiFi power saving (critical for stable connections)
- Create Python virtual environment (`.venv`)
- Install pip dependencies

```bash
bash install_pi.sh
```

**User prompts during installation:**
- Pay attention to messages about rclone setup and configuration requirements
- The script will show instructions for next steps

Example output:
```
[1/4] Updating apt and installing system dependencies...
[1.5/4] Disabling WiFi power saving...
[2/4] Setting up Python dependencies...
[2.5/4] Cleaning up legacy service files...
[3/4] Google Drive (rclone) setup...
[4/4] Final Setup...
```

---

## Step 6: Create Device Configuration File (`config_WM.py`)

This file contains device-specific settings that are NOT version-controlled.

```bash
nano config_WM.py
```

Enter the following content (adjust `device_id` for your specific device):

```python
# Device-specific configuration (DO NOT commit to Git)
# This device ID must match entries in credentials_store.csv

device_id = "RETROFIT-01"  # Change to your device ID (e.g., RETROFIT-01, RETROFIT-02, etc.)
```

Save and exit: `Ctrl+X` → `Y` → `Enter`

**Important:** This is in `.gitignore`, it will NOT be overwritten by git updates.

---

## Step 7: Create Device Credentials File (`credentials_store.csv`)

```bash
nano credentials_store.csv
```

Enter the following content (update all values for your setup):

```csv
device_id,node_name,gdrive_folder_id,thingspeak_channel_id,thingspeak_write_api_key
RETROFIT-01,Meter-Sensor-01,<YOUR_GDRIVE_FOLDER_ID>,<YOUR_THINGSPEAK_CHANNEL>,<YOUR_THINGSPEAK_API_KEY>
```

**Fields explained:**
- `device_id`: Must match config_WM.py
- `node_name`: Friendly name for the device
- `gdrive_folder_id`: Google Drive folder ID where images are uploaded
- `thingspeak_channel_id`: ThingSpeak channel ID (numeric)
- `thingspeak_write_api_key`: ThingSpeak write API key

**To find Google Drive Folder ID:**
1. Open https://drive.google.com
2. Create a folder or navigate to your folder
3. Look at the URL: `https://drive.google.com/drive/folders/FOLDER_ID_HERE?usp=sharing`
4. Copy the FOLDER_ID

**Example:**
```csv
device_id,node_name,gdrive_folder_id,thingspeak_channel_id,thingspeak_write_api_key
RETROFIT-01,Kitchen-Meter,1a2b3c4d5e6f7g8h9i0j,3275001,FOU6A6Z5UPM99P2W
```

Save and exit: `Ctrl+X` → `Y` → `Enter`

**Important:** This is in `.gitignore`, it will NOT be overwritten by git updates. Contains sensitive credentials.

---

## Step 8: Configure rclone for Google Drive Access

rclone is used to upload images to Google Drive securely.

```bash
rclone config
```

**Follow the interactive prompts:**

1. **New remote name:** Type `gdrive` and press Enter

2. **Storage type:** Type `drive` and press Enter

3. **Google Application Client ID:** Leave blank and press Enter (uses default)

4. **Google Application Client Secret:** Leave blank and press Enter (uses default)

5. **Scope:** Type `1` (Full access) and press Enter

6. **Root folder ID:** Leave blank and press Enter

7. **Service account file:** Leave blank and press Enter (uses OAuth)

8. **Auto config:** Type `y` and press Enter
   - Browser will open for Google authentication
   - Login with your Google account
   - Grant access to rclone
   - Copy the code shown and paste into terminal

9. **Confirm:** When asked "Is this ok?" type `y` and press Enter

10. **Edit config again?** Type `n` and press Enter (Done)

**Verify rclone is configured:**
```bash
rclone listremotes
# Output: gdrive
```

**Test rclone access:**
```bash
rclone lsd gdrive:
# Should list your Google Drive folders
```

---

## Step 9: Install systemd Service

The installer created a temporary service file. Install it as a system service:

```bash
sudo cp /tmp/retrofit-capture.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable retrofit-capture.service
```

Verify service is registered:
```bash
sudo systemctl list-unit-files | grep retrofit-capture
# Output: retrofit-capture.service  enabled
```

---

## Step 10: Enable Automatic OTA Updates (Optional)

To automatically update code every 30 minutes:

```bash
# Add cron job for automatic updates
(crontab -l 2>/dev/null; echo "*/30 * * * * cd $(pwd) && ./update.sh >> update.log 2>&1") | crontab -
```

Verify cron is set:
```bash
crontab -l
```

---

## Step 11: Start the Service

```bash
sudo systemctl start retrofit-capture.service
```

Verify it started:
```bash
sudo systemctl status retrofit-capture.service
```

Expected output:
```
● retrofit-capture.service - RetroFit Image Capture Service v2.1
     Loaded: loaded (/etc/systemd/system/retrofit-capture.service)
     Active: active (running) since ...
```

---

## Step 12: Monitor Service Logs

Watch the service in real-time:

```bash
sudo journalctl -u retrofit-capture.service -f
```

Exit monitoring: `Ctrl+C`

To see past logs:
```bash
sudo journalctl -u retrofit-capture.service -n 50
# Shows last 50 log lines
```

---

## Step 13: Verify Operation

Check health monitoring file (updated every cycle):

```bash
cat /tmp/health.json
```

Example output:
```json
{
  "device_id": "RETROFIT-01",
  "status": "running",
  "timestamp": "2026-03-13T10:30:45.123456",
  "message": "Cycle #42: success",
  "uptime_cycles": 42,
  "success_count": 40,
  "backlog_size": 0,
  "free_disk_mb": 450.2,
  "cpu_temp_c": 48.5
}
```

Check persistent health copy (updated every 10 cycles):
```bash
cat health.json
```

---

## Troubleshooting

### Service won't start
```bash
# Check logs for errors
sudo journalctl -u retrofit-capture.service -n 100
```

Common issues:
- **"config_WM.py not found"** → Create `config_WM.py` (Step 6)
- **"credentials_store.csv not found"** → Create `credentials_store.csv` (Step 7)
- **"rclone: not configured"** → Run `rclone config` (Step 8)
- **"device_id mismatch"** → Ensure device_id in config_WM.py matches credentials_store.csv

### WiFi disconnects
```bash
# Check WiFi interface
iwconfig wlan0

# Verify power saving is disabled (should show "Power Management:off")
```

### High CPU temperature
```bash
# Check CPU temperature
vcgencmd measure_temp

# If above 80°C, check for background processes
top
```

### Restart service
```bash
sudo systemctl restart retrofit-capture.service

# Or stop and start
sudo systemctl stop retrofit-capture.service
sudo systemctl start retrofit-capture.service
```

### View captured images
```bash
ls -lh capture_output/
# Shows all captured images with timestamps
```

---

## Post-Deployment Verification

After deployment, verify:

1. **Service is running:**
   ```bash
   sudo systemctl is-active retrofit-capture.service
   # Output: active
   ```

2. **Service restarts on reboot:**
   ```bash
   sudo systemctl is-enabled retrofit-capture.service
   # Output: enabled
   ```

3. **Images are captured:**
   ```bash
   ls capture_output/ | wc -l
   # Should increase after each cycle (every 5 minutes by default)
   ```

4. **Images are uploaded to Google Drive:**
   - Check your Google Drive folder (from credentials_store.csv)
   - Should see new images with timestamps

5. **ThingSpeak is receiving data:**
   - Log into your ThingSpeak channel
   - Check "Recent Entries" in Channel View
   - Should see status codes (0, 1, or 2) in Field 1

6. **Health monitoring is working:**
   ```bash
   cat health.json | grep cpu_temp_c
   # Should show CPU temperature
   ```

---

## File Structure After Deployment

```
/home/pi/RetroFit/Flow-1/
├── main_service.py                    # Main service loop
├── config.py                          # Global constants
├── config_WM.py                       # Device-specific config (created in Step 6)
├── credentials_store.csv              # Device credentials (created in Step 7)
├── install_pi.sh                      # Installer script
├── update.sh                          # OTA update script
├── requirements.txt                   # Python dependencies
├── retrofit-capture.service           # Systemd service file
├── Dockerfile                         # Docker image definition
├── .req_hash                          # Pip requirements hash (auto-created)
├── capture_output/                    # Captured images directory
├── health.json                        # Health monitoring (persistent copy)
├── error.log                          # Error log file
├── update.log                         # Update log file
└── src/
    ├── __init__.py
    ├── capture.py                     # Camera interface
    ├── roi_extractor.py               # ArUco marker ROI extraction
    ├── rclone_uploader.py             # Google Drive uploader
    ├── thingspeak_reporter.py         # ThingSpeak status reporter
    └── credential_manager.py          # Credential loader
```

---

## Maintenance & Updates

### Automatic Updates
The service automatically pulls updates from GitHub every 30 minutes via `update.sh` cron job.

### Manual Update
```bash
cd /home/pi/RetroFit/Flow-1
bash update.sh
```

### View Update Log
```bash
tail -50 update.log
```

### Revert to Previous Version
```bash
cd /home/pi/RetroFit/Flow-1
git log --oneline  # Show commit history
git checkout <COMMIT_HASH>  # Revert to specific commit
sudo systemctl restart retrofit-capture.service
```

---

## Important Notes

### DO NOT EDIT (Version Controlled)
- main_service.py
- config.py
- install_pi.sh
- update.sh
- retrofit-capture.service
- Dockerfile
- requirements.txt
- src/ files

Any changes to these will be overwritten by git updates. Make changes in the GitHub repository instead.

### SAFE TO EDIT (Ignored by Git)
- config_WM.py
- credentials_store.csv
- Variable.txt (if present)
- var2.txt (if present)

These files are in `.gitignore` and will NOT be overwritten.

---

## Contact & Support

**Repository:** https://github.com/aditya08deole/Flow-1.git

For issues or questions:
1. Check service logs: `sudo journalctl -u retrofit-capture.service -n 100`
2. Verify configuration files (config_WM.py, credentials_store.csv)
3. Test rclone access: `rclone lsd gdrive:`
4. Check GitHub repository for updates

---

## Version History

**v2.1 (Current)**
- Fixed venv path mismatch
- Fixed infinite restart loops
- Improved WiFi stability (lowered CPU quota, disabled power saving)
- Fixed SD card wear (health file to tmpfs)
- Added thermal monitoring
- Added WiFi connectivity checks
- Conditional pip install
- Docker opencv-python-headless support
- Exit code contract for proper restart handling

---

**Last Updated:** 2026-03-13
**Repository:** https://github.com/aditya08deole/Flow-1.git
