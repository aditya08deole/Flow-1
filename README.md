# RetroFit EvaraFlow v2.1

**Raspberry Pi Zero W Image Capture & Cloud Upload Service**

[![Repository](https://img.shields.io/badge/Repo-Flow--1-blue?logo=github)](https://github.com/aditya08deole/Flow-1.git)
[![Version](https://img.shields.io/badge/Version-2.1-brightgreen)]()
[![Status](https://img.shields.io/badge/Status-Production--Ready-success)]()

---

## Overview

RetroFit EvaraFlow is a lightweight, production-grade image capture service optimized for **Raspberry Pi Zero W**. It captures meter/sensor images, extracts regions-of-interest (ROI) using ArUco markers, uploads to Google Drive, and reports status to ThingSpeak.

**Key Features:**
- ✅ Automated image capture with GPIO LED control
- ✅ ArUco marker-based ROI extraction (automatic perspective correction)
- ✅ Google Drive cloud upload with bandwidth limiting
- ✅ ThingSpeak status reporting (live monitoring)
- ✅ Automatic OTA updates via GitHub (every 30 minutes)
- ✅ WiFi resilience & connectivity monitoring
- ✅ Thermal & health monitoring via `/tmp/health.json`
- ✅ Systemd service integration (auto-restart on reboot)
- ✅ SD card wear protection (tmpfs health file)
- ✅ Docker support

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    RetroFit Service Loop (5 min interval)       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. PRE-CHECK PHASE                                             │
│     └─ Check WiFi connectivity (ping 8.8.8.8)                  │
│     └─ Verify disk space (>50 MB)                              │
│                                                                 │
│  2. CAPTURE PHASE (PiCamera2)                                   │
│     └─ Capture image at configured resolution                  │
│     └─ GPIO LED control (on during capture)                    │
│                                                                 │
│  3. ROI EXTRACTION PHASE (OpenCV + ArUco)                       │
│     └─ Detect ArUco markers in image                           │
│     └─ Extract ROI (Region of Interest) via perspective warp   │
│     └─ Cache ROI coordinates (30-minute validity)              │
│     └─ Fall back to full image if markers not found            │
│                                                                 │
│  4. UPLOAD PHASE (rclone + Google Drive)                        │
│     └─ Upload ROI/full image to Google Drive folder            │
│     └─ Bandwidth limit: 1 Mbps (respects WiFi management)      │
│     └─ Queue failed uploads for retry                          │
│                                                                 │
│  5. STATUS REPORTING PHASE (ThingSpeak)                         │
│     └─ Send status code to ThingSpeak field1:                  │
│        • 1 = ArUco detected + upload success                   │
│        • 0 = No ArUco detected + upload success                │
│        • 2 = Any error (capture/upload fail)                   │
│                                                                 │
│  6. HEALTH & CLEANUP PHASE                                      │
│     └─ Write health.json to /tmp (tmpfs - no SD wear)          │
│     └─ Periodic SD copy every 10 cycles (~1 hour)              │
│     └─ Record CPU temperature via vcgencmd                     │
│     └─ Clean up old images (keep last 50)                      │
│                                                                 │
│  7. SLEEP                                                       │
│     └─ Wait for next cycle (default: 5 minutes)                │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## System Requirements

**Hardware:**
- Raspberry Pi Zero W (or Pi 3B+/4B for higher performance)
- 32 GB+ microSD card (Class 10, UHS-I recommended)
- PiCamera/PiCamera2 module
- 5V/2A USB power adapter
- LED + resistor for GPIO pin 23 (optional, service handles missing GPIO)

**Software:**
- Raspberry Pi OS (Bookworm or later)
- Python 3.8+
- rclone (for Google Drive access)
- systemd (for service management)

---

## Installation

### Quick Start (5-10 minutes)

1. **SSH into Raspberry Pi**
   ```bash
   ssh pi@<RPI_IP>
   ```

2. **Clone repository**
   ```bash
   mkdir -p ~/RetroFit && cd ~/RetroFit
   git clone https://github.com/aditya08deole/Flow-1.git
   cd Flow-1
   ```

3. **Run installer**
   ```bash
   bash install_pi.sh
   ```

4. **Configure device**
   ```bash
   # Create device config
   nano config_WM.py
   # Add: device_id = "RETROFIT-01"

   # Create credentials
   nano credentials_store.csv
   # Add: device_id,node_name,gdrive_folder_id,thingspeak_channel_id,thingspeak_write_api_key
   ```

5. **Configure rclone**
   ```bash
   rclone config  # Select: create new remote "gdrive" using Google Drive
   ```

6. **Install service**
   ```bash
   sudo cp /tmp/retrofit-capture.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable retrofit-capture.service
   sudo systemctl start retrofit-capture.service
   ```

7. **Monitor**
   ```bash
   sudo journalctl -u retrofit-capture.service -f
   ```

**For detailed step-by-step instructions, see [DEPLOYMENT.md](DEPLOYMENT.md)**

---

## Configuration

### Device Configuration (`config_WM.py`)
```python
device_id = "RETROFIT-01"  # Unique device identifier (must be in credentials_store.csv)
```

### Credentials (`credentials_store.csv`)
```csv
device_id,node_name,gdrive_folder_id,thingspeak_channel_id,thingspeak_write_api_key
RETROFIT-01,Meter-Sensor-01,<FOLDER_ID>,<CHANNEL_ID>,<API_KEY>
```

### Global Settings (`config.py`)
```python
# Capture settings
CAPTURE_INTERVAL_MINUTES = 5
CAMERA_RESOLUTION = (1280, 960)
JPEG_QUALITY = 85

# rclone settings
RCLONE_REMOTE_NAME = "gdrive"
RCLONE_BANDWIDTH_LIMIT = "1M"  # Prevents WiFi saturation
UPLOAD_TIMEOUT = 120  # seconds

# Various thresholds...
```

---

## Features in Detail

### 🎥 Image Capture
- Native PiCamera2 support (auto-detects fallback to picamera)
- GPIO LED control during capture
- Configurable resolution & JPEG quality
- Automatic memory cleanup (OpenCV buffers freed)

### 📍 ArUco ROI Extraction
- Automatic marker detection (4 corners for perspective correction)
- Smart caching: ROI coordinates valid for 30 minutes
- Falls back to full image if markers not detected
- Tracks ArUco detection streaks (warning after 6 failures)

### ☁️ Google Drive Upload
- Uses rclone for reliable, authenticated uploads
- Bandwidth limiting (1 Mbps default) to preserve WiFi for management frames
- Upload retry logic with backlog queue (up to 20 items)
- Verification: checks file size on GDrive matches local

### 📊 ThingSpeak Monitoring
- Real-time status reporting (every cycle)
- Status codes: 1=ArUco success, 0=full image, 2=error
- Rate limiting: minimum 15 seconds between updates (respects API limits)
- Visible logging (changed from silent debug to INFO level)

### 🔄 Automatic Updates
- OTA via `update.sh` cron job (every 30 minutes)
- Conditional pip install (only if requirements.txt changed)
- EXIT trap ensures service restarts even on update failure
- Git conflict prevention via `git checkout -- .`

### 📡 WiFi Resilience
- WiFi connectivity check before each cycle (ping 8.8.8.8)
- Power saving disabled (via iwconfig + NetworkManager)
- CPU quota lowered to 60% (allows wpa_supplicant to run)
- Bandwidth limiting prevents WiFi saturation
- Automatic reconnect logic

### 🌡️ Health Monitoring
- CPU temperature via vcgencmd
- Free disk space tracking
- Success rate & uptime cycles
- Backlog size monitoring
- Written to `/tmp/health.json` (tmpfs - no SD wear)
- Periodic SD copy every 10 cycles

### 🔧 Systemd Service
- `Restart=on-failure` (not `always` - prevents infinite loops)
- Proper exit code contract: 2=config error, 3=credential error, 1=transient crash
- `RestartPreventExitStatus=2 3` (fatal errors don't restart)
- Resource limits: `CPUQuota=60%`, `MemoryMax=300M`
- Waits for `network-online.target` before starting

---

## File Structure

```
Flow-1/
├── main_service.py              # Main service loop (9-step capture pipeline)
├── config.py                    # Global configuration & constants
├── config_WM.py                 # Device-specific config (user-created, .gitignored)
├── credentials_store.csv        # Device credentials (user-created, .gitignored)
├── install_pi.sh                # One-time installer
├── update.sh                    # OTA update script (cron: */30)
├── requirements.txt             # Python dependencies
├── retrofit-capture.service     # systemd service file
├── Dockerfile                   # Docker image definition
├── DEPLOYMENT.md                # Complete deployment guide
├── README.md                    # This file
├── error.log                    # Error log (RotatingFileHandler 2MB max)
├── health.json                  # Health monitoring (persistent)
├── capture_output/              # Captured images directory
├── src/
│   ├── __init__.py
│   ├── capture.py               # PiCamera/PiCamera2 interface + GPIO
│   ├── roi_extractor.py         # ArUco detection + perspective warp
│   ├── rclone_uploader.py       # Google Drive uploader (rclone wrapper)
│   ├── thingspeak_reporter.py   # ThingSpeak HTTP API client
│   └── credential_manager.py    # CSV credential loader
└── utils/
    ├── aruco_generator.py       # Generate ArUco markers for printing
    ├── setup_view.py            # Visualization tool
    └── marker_*.png             # Pre-generated marker images
```

---

## Exit Codes & Restart Behavior

| Exit Code | Meaning | Systemd Restart? |
|-----------|---------|-----------------|
| 0 | Graceful shutdown (SIGTERM) | ❌ No |
| 1 | Transient crash (unexpected) | ✅ Yes (up to 3 times) |
| 2 | Config error (fatal) | ❌ No (RestartPreventExitStatus) |
| 3 | Credential error (fatal) | ❌ No (RestartPreventExitStatus) |

This prevents infinite restart loops when config is misconfigured.

---

## Troubleshooting

### Service won't start
```bash
sudo journalctl -u retrofit-capture.service -n 100
```

**Common causes:**
- Missing `config_WM.py` → Create with device_id
- Missing `credentials_store.csv` → Create with credentials
- rclone not configured → Run `rclone config`
- Device ID mismatch → Ensure match between two files

### WiFi keeps disconnecting
```bash
iwconfig wlan0  # Should show "Power Management:off"
```

**Fixes:**
- Already applied: Disabled power saving, lowered CPU quota, bandwidth limited
- Verify: `grep -i "power saving" install.log`

### High CPU/memory usage
```bash
top
vcgencmd measure_temp  # Should be <80°C
```

**Possible causes:**
- OpenCV processing on high-resolution images
- Large backlog of failed uploads
- CPU thermal throttling (>80°C)

### Capture not uploaded
```bash
rclone lsd gdrive:  # Verify rclone access
ls capture_output/  # Check if images are captured
tail health.json    # Check last status
```

---

## Performance Characteristics

**On Raspberry Pi Zero W:**
- Capture duration: ~1-2 seconds
- ROI extraction: ~0.5-1 second
- Google Drive upload: 5-30 seconds (depends on image size & WiFi)
- **Total cycle time:** ~10-40 seconds (full cycle every 5 minutes)

**Memory Usage:**
- Service baseline: ~50-70 MB
- Peak during capture: ~150-200 MB
- MemoryMax limit: 300 MB (prevents OOM crashes)

**SD Card Writes:**
- Image captures: ~100 KB per image (~1.2 MB per day at 5-min intervals)
- Health file: Reduced from ~288x/day to ~29x/day (10-cycle intervals)
- Health tmpfs: All frequent writes go to RAM (`/tmp/health.json`)

---

## Docker Support

For testing or non-Pi deployments:

```bash
# Build image
docker build -t retrofit-flow .

# Run container
docker-compose up -d

# View logs
docker-compose logs -f
```

**Note:** Camera support only available on Raspberry Pi. Docker is for testing other components.

---

## Security Considerations

- ✅ Credentials stored in CSV (excluded from Git)
- ✅ rclone uses OAuth 2.0 for Google Drive (no password stored)
- ✅ ThingSpeak API key in credentials CSV (protected)
- ⚠️  Always use `https://` for external services
- ⚠️  Keep SSH keys & credentials private
- ⚠️  Review `.gitignore` to ensure sensitive files are excluded

---

## Contributing & Support

**Issues or questions?**
1. Check [DEPLOYMENT.md](DEPLOYMENT.md) troubleshooting section
2. Review logs: `sudo journalctl -u retrofit-capture.service -n 100`
3. Check GitHub issues: https://github.com/aditya08deole/Flow-1/issues

**For improvements:**
- Fork the repository
- Create a feature branch
- Submit a pull request

---

## License

See LICENSE file for details.

---

## Version History

### v2.1 (Current - March 2026)
**Major Stability Release**
- 🔧 Fixed venv path mismatch (.venv consistency)
- 🔧 Fixed infinite restart loops (Restart=on-failure + RestartPreventExitStatus)
- 🔧 Fixed service stopping on update failure (EXIT trap added)
- 📈 Improved WiFi stability (CPUQuota 60%, power-save disabled, bwlimit 1M)
- 📈 SD card wear protection (tmpfs health file)
- 📈 Added thermal monitoring (CPU temp in health.json)
- 📈 Added WiFi connectivity checks (ping before upload)
- 📈 Conditional pip install (hash-based, skips if unchanged)
- 📈 Docker support (opencv-python-headless layer)
- 📈 Proper exit codes (2=config, 3=credential, 1=transient)

### v2.0
- Initial production release

---

## Repository

**Primary URL:** https://github.com/aditya08deole/Flow-1.git

---

**Last Updated:** 2026-03-13
**Maintained by:** RetroFit Team
