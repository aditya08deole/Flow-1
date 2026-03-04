#!/bin/bash
# RetroFit Image Capture Service - Simple OTA updater
set -e

echo "Stopping service..."
sudo systemctl stop retrofit-capture.service || true

echo "Pulling latest changes..."
git pull

# Check if resolving via Docker native configs
if [ -f "docker-compose.yml" ] && command -v docker-compose &> /dev/null; then
    echo "Docker environment detected..."
    echo "Rebuilding and restarting Docker container..."
    docker-compose down
    docker-compose build
    docker-compose up -d
else
    echo "Native environment detected..."
    echo "Installing/updating dependencies within venv..."
    if [ ! -d "venv" ]; then
        python3 -m venv venv
    fi
    source venv/bin/activate
    pip install -r requirements.txt
    deactivate

    echo "Starting standard systemd service..."
    sudo systemctl start retrofit-capture.service
fi

echo "Update complete!"
