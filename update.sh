#!/bin/bash
# RetroFit Image Capture Service - Simple OTA updater
set -e

echo "[1/4] Stopping service..."
sudo systemctl stop retrofit-capture.service || true

echo "[2/4] Resetting local file changes..."
git checkout -- .

echo "[3/4] Pulling latest changes from GitHub..."
git pull

echo "[4/4] Synchronizing environment..."
# Check if resolving via Docker native configs
if [ -f "docker-compose.yml" ] && command -v docker-compose &> /dev/null; then
    echo "   -> Docker environment detected..."
    docker-compose down
    docker-compose build
    docker-compose up -d
else
    echo "   -> Native environment detected..."
    if [ ! -d "venv" ]; then
        python3 -m venv --system-site-packages venv
    fi
    source venv/bin/activate
    pip install --no-cache-dir -r requirements.txt
    deactivate

    echo "   -> Restarting systemd service..."
    sudo systemctl start retrofit-capture.service
fi

echo "Update complete!"
