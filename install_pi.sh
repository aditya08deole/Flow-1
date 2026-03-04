#!/bin/bash
# RetroFit Image Capture Service - Pi Zero W Installer
set -e

echo "==========================================="
echo "RetroFit Capture Service - Pi OS Installer"
echo "==========================================="

echo "[1/4] Updating apt and installing system dependencies..."
sudo apt-get update
sudo apt-get install -y python3-pip python3-venv libatlas-base-dev rclone

echo "[2/4] Setting up Python dependencies..."
# Utilizing a virtual environment to avoid --break-system-packages overrides
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install -r requirements.txt
deactivate

echo "[3/4] Google Drive (rclone) setup..."
echo "You must configure rclone to connect to Google Drive."
echo "Run: 'rclone config' and create a remote named 'gdrive'."

echo "[4/4] Final Setup..."
echo "Please ensure you have placed 'credentials_store.csv' and 'config_WM.py' in this directory."
echo "Then, you can install the systemd service by running:"

# Update service file exactly to the cloned working directory
CURRENT_DIR=$(pwd)
sed -i "s|/opt/retrofit/Ph-03-main|$CURRENT_DIR|g" retrofit-capture.service

echo "sudo cp retrofit-capture.service /etc/systemd/system/"
echo "sudo systemctl daemon-reload"
echo "sudo systemctl enable retrofit-capture.service"
echo "sudo systemctl start retrofit-capture.service"

echo "Installation script completed!"
