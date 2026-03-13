#!/bin/bash
# RetroFit Image Capture Service - Pi Zero W Installer
# Repository: https://github.com/aditya08deole/Flow-1.git
# Documentation: See DEPLOYMENT.md for complete setup guide

echo "==========================================="
echo "RetroFit Capture Service - Pi OS Installer"
echo "==========================================="

echo "[1/4] Updating apt and installing system dependencies..."
sudo apt-get update
# python3-skimage, python3-sklearn, python3-joblib installed via apt to avoid
# armhf source compilation failures (no piwheels wheels for recent versions)
sudo apt-get install -y python3-pip python3-venv python3-numpy python3-opencv \
    libatlas-base-dev rclone libglib2.0-0 \
    python3-skimage python3-sklearn python3-joblib

echo "[1.5/4] Disabling WiFi power saving (prevents disconnects during uploads)..."
sudo iwconfig wlan0 power off || true
sudo iw dev wlan0 set power_save off || true
sudo mkdir -p /etc/NetworkManager/conf.d
printf '[connection]\nwifi.powersave = 2\n' | sudo tee /etc/NetworkManager/conf.d/wifi-powersave.conf > /dev/null
echo "  -> WiFi power save disabled (immediate + persistent on reboot)"

echo "[2/4] Setting up Python dependencies..."
# Utilizing a virtual environment to avoid --break-system-packages overrides
if [ ! -d ".venv" ]; then
    python3 -m venv --system-site-packages .venv
fi
source .venv/bin/activate
pip install --no-cache-dir -r requirements.txt
deactivate

echo "[2.5/4] Cleaning up legacy service files..."
if sudo systemctl is-enabled codetest.service > /dev/null 2>&1 || \
   sudo systemctl is-active codetest.service > /dev/null 2>&1; then
    echo "  -> Disabling legacy codetest.service..."
    sudo systemctl stop codetest.service || true
    sudo systemctl disable codetest.service || true
    sudo rm -f /etc/systemd/system/codetest.service
    sudo systemctl daemon-reload
    echo "  -> Legacy service removed."
fi

echo "[3/4] Google Drive (rclone) setup..."
echo "You must configure rclone to connect to Google Drive."
echo "Run: 'rclone config' and create a remote named 'gdrive'."

echo "[4/4] Final Setup..."
echo "Please ensure you have placed 'credentials_store.csv' and 'config_WM.py' in this directory."
echo "Then, you can install the systemd service by running:"

# Create a modified copy of the service file (do NOT modify the git-tracked original)
CURRENT_DIR=$(pwd)
CURRENT_USER=$(whoami)
cp retrofit-capture.service /tmp/retrofit-capture.service
sed -i "s|/opt/retrofit/Ph-03-main|$CURRENT_DIR|g" /tmp/retrofit-capture.service
sed -i "s|User=pi|User=$CURRENT_USER|g" /tmp/retrofit-capture.service

echo ""
echo "To install and start the service, run these commands:"
echo "sudo cp /tmp/retrofit-capture.service /etc/systemd/system/"
echo "sudo systemctl daemon-reload"
echo "sudo systemctl enable retrofit-capture.service"
echo "sudo systemctl start retrofit-capture.service"

echo ""
echo "[Optional] To enable automatic OTA updates every 30 minutes, run:"
echo "(crontab -l 2>/dev/null; echo \"*/30 * * * * cd $CURRENT_DIR && ./update.sh >> update.log 2>&1\") | crontab -"

echo "Installation script completed!"
