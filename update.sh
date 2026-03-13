#!/bin/bash
# RetroFit Image Capture Service - Simple OTA updater
# Repository: https://github.com/aditya08deole/Flow-1.git
# Pulls latest changes and updates dependencies automatically every 30 minutes

# Always restart the service on script exit (success or failure), native mode only
_ensure_service_running() {
    if ! ([ -f "docker-compose.yml" ] && command -v docker-compose > /dev/null 2>&1); then
        echo "   -> Ensuring systemd service is running..."
        sudo systemctl start retrofit-capture.service || true
    fi
}
trap _ensure_service_running EXIT

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
    if [ ! -d ".venv" ]; then
        python3 -m venv --system-site-packages .venv
    fi
    source .venv/bin/activate

    CURRENT_HASH=$(md5sum requirements.txt | awk '{print $1}')
    STORED_HASH=$(cat .req_hash 2>/dev/null || echo "")
    if [ "$CURRENT_HASH" != "$STORED_HASH" ]; then
        echo "   -> requirements.txt changed — installing dependencies..."
        pip install --no-cache-dir -r requirements.txt && echo "$CURRENT_HASH" > .req_hash
    else
        echo "   -> requirements.txt unchanged — skipping pip install."
    fi

    deactivate
    # Service restart is handled by the EXIT trap above
fi

echo "Update complete!"
