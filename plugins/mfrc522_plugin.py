#!/usr/bin/env python3
import os
import sys
import signal
import time
import datetime

# Ensure current plugin folder is in sys.path so MFRC522.py is found
sys.path.insert(0, os.path.dirname(__file__))

try:
    import MFRC522
    MFRC522_AVAILABLE = True
except ImportError:
    MFRC522_AVAILABLE = False

if not MFRC522_AVAILABLE:
    print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
          "MFRC522 Python library not available on this system. "
          "Plugin will still load but cannot read cards.")
    # Stop here since we can't read cards
    sys.exit(0)

continue_reading = True

# Function to convert UID list to string
def uidToString(uid):
    return ''.join(format(i, '02X') for i in uid[::-1])  # reversed like your read.py

# Capture SIGINT for cleanup when the script is aborted
def end_read(signal, frame):
    global continue_reading
    print("Ctrl+C captured, ending read.")
    continue_reading = False

# Hook the SIGINT
signal.signal(signal.SIGINT, end_read)

# Create an object of the MFRC522 class
MIFAREReader = MFRC522.MFRC522()

# Welcome message
print("Welcome to the MFRC522 plugin reader")
print("Press Ctrl-C to stop.")

# Main loop to scan for cards
while continue_reading:
    (status, TagType) = MIFAREReader.MFRC522_Request(MIFAREReader.PICC_REQIDL)
    
    if status == MIFAREReader.MI_OK:
        print("Card detected")
        
        (status, uid) = MIFAREReader.MFRC522_SelectTagSN()
        if status == MIFAREReader.MI_OK:
            print(f"Card read UID: {uidToString(uid)}")
        else:
            print("Authentication error")
    
    time.sleep(0.5)  # small delay to reduce CPU usage
