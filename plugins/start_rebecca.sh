#!/bin/bash
set -e

echo "Rebecca Starting up..." >&2

if ! lsmod | grep -q "^i2c_dev"; then
    echo "Rebecca Loading i2c-dev module.." >&2
    sudo modprobe i2c-dev
fi

echo "rebecca Waiting for /dev/ic2-1..."
for i in {1..30}; do
    if [ -e /dev/i2c-1 ]; then
       echo"Rebecca I2C device found" >&2
       break
    fi
    sleep 1
done

if [ ! -e /dev/i2c-1 ]; then
    echo "Rebecca ERROR: I2C device not found after 30s!" >&2
    exit 1
fi

source /home/kali/overlay_launcher/overlay_launcher_env/bin/activate
echo "rebecca launching rebecca.py..." >&2
exec python3 /home/kali/overlay_launcher/plugins/rebecca.py
