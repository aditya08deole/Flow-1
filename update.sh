#!/bin/bash
# RetroFit Image Capture Service - Robust OTA updater with Rollback
# Repository: https://github.com/aditya08deole/Flow-1.git

LOG_FILE="update.log"
SERVICE_NAME="retrofit-capture.service"

echo "--- Update Started: $(date) ---" | tee -a "$LOG_FILE"

# 1. Snapshot current state
PREV_HASH=$(git rev-parse HEAD)
echo "[1/5] Snapshotting current version: $PREV_HASH" | tee -a "$LOG_FILE"

# 2. Stop service
echo "[2/5] Stopping service..." | tee -a "$LOG_FILE"
sudo systemctl stop "$SERVICE_NAME" || true

# 3. Pull latest code
echo "[3/5] Updating code from GitHub..." | tee -a "$LOG_FILE"
git checkout -- .
git pull | tee -a "$LOG_FILE"

# 3.5 Check for service file changes
if git diff "$PREV_HASH" HEAD --name-only 2>/dev/null | grep -q "$SERVICE_NAME"; then
    echo "   -> Service file changed — reinstalling..." | tee -a "$LOG_FILE"
    CURRENT_DIR=$(pwd)
    CURRENT_USER=$(whoami)
    cp "$SERVICE_NAME" /tmp/"$SERVICE_NAME"
    sed -i "s|__INSTALL_DIR__|$CURRENT_DIR|g" /tmp/"$SERVICE_NAME"
    sed -i "s|__SERVICE_USER__|$CURRENT_USER|g" /tmp/"$SERVICE_NAME"
    sudo cp /tmp/"$SERVICE_NAME" /etc/systemd/system/"$SERVICE_NAME"
    sudo systemctl daemon-reload
fi

# 4. Sync environment
echo "[4/5] Synchronizing environment..." | tee -a "$LOG_FILE"
if [ ! -d ".venv" ]; then
    python3 -m venv --system-site-packages .venv
fi
source .venv/bin/activate

CURRENT_HASH=$(md5sum requirements.txt | awk '{print $1}')
STORED_HASH=$(cat .req_hash 2>/dev/null || echo "")
if [ "$CURRENT_HASH" != "$STORED_HASH" ]; then
    echo "   -> Installing dependencies..." | tee -a "$LOG_FILE"
    pip install --no-cache-dir -r requirements.txt && echo "$CURRENT_HASH" > .req_hash
fi

# 4.5 Integrity check (Syntax test)
echo "   -> Validating script integrity..." | tee -a "$LOG_FILE"
if ! python3 -m py_compile main_service.py; then
    echo "❌ ERROR: Syntax error detected in new code! Rolling back..." | tee -a "$LOG_FILE"
    git reset --hard "$PREV_HASH"
    deactivate
    sudo systemctl start "$SERVICE_NAME"
    exit 1
fi
deactivate

# 5. Restart and Health Check
echo "[5/5] Restarting and verifying health..." | tee -a "$LOG_FILE"
sudo systemctl start "$SERVICE_NAME"
sleep 10 # Wait for service to initialize

if sudo systemctl is-active --quiet "$SERVICE_NAME"; then
    echo "✅ Update successful: $(git rev-parse --short HEAD)" | tee -a "$LOG_FILE"
else
    echo "❌ ERROR: Service failed to start after update! Rolling back to $PREV_HASH..." | tee -a "$LOG_FILE"
    git reset --hard "$PREV_HASH"
    sudo systemctl restart "$SERVICE_NAME"
    echo "⚠️  System rolled back to previous stable version." | tee -a "$LOG_FILE"
    exit 1
fi

echo "--- Update Finished: $(date) ---" | tee -a "$LOG_FILE"
