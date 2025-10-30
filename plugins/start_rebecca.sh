#!/bin/bash
set -e

# Log to systemd journal
echo "[Rebecca] Starting up..." >&2

# Ensure I2C driver is loaded
if ! lsmod | grep -q "^i2c_dev"; then
    echo "[Rebecca] Loading i2c-dev module..." >&2
    sudo modprobe i2c-dev
fi

# Wait until /dev/i2c-1 exists
echo "[Rebecca] Waiting for /dev/i2c-1..."
for i in {1..30}; do
    if [ -e /dev/i2c-1 ]; then
        echo "[Rebecca] I2C device found." >&2
        break
    fi
    sleep 1
done

if [ ! -e /dev/i2c-1 ]; then
    echo "[Rebecca] ERROR: I2C device not found after 30s!" >&2
    exit 1
fi

# Activate Python virtual environment
source /home/kali/overlay_launcher/overlay_launcher_env/bin/activate

# Start Rebecca
echo "[Rebecca] Launching rebecca.py..." >&2
exec python3 /home/kali/overlay_launcher/plugins/rebecca.py
