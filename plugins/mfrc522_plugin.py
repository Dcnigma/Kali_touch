#!/usr/bin/env python3
import tkinter as tk
from tkinter import scrolledtext
import threading
import time
import os, sys
plugin_dir = os.path.dirname(os.path.abspath(__file__))
if plugin_dir not in sys.path:
    sys.path.insert(0, plugin_dir)

try:
    import MFRC522
except ImportError:
    MFRC522 = None
    
class MFRC522Plugin:
    def __init__(self, parent=None, *args, **kwargs):
        # Store launcher data
        self.root = parent or tk.Tk()
        self.cfg = kwargs.get("cfg", {})
        self.apps = kwargs.get("apps", {})

        # Window setup
        self.root.title("MFRC522 RFID Reader")
        self.root.geometry("800x900")

        # Label at the top
        self.label = tk.Label(self.root, text="Scan a card...", font=("Helvetica", 24))
        self.label.pack(pady=40)

        # Log box for card UIDs
        self.log_box = scrolledtext.ScrolledText(self.root, state=tk.DISABLED, font=("Courier", 14))
        self.log_box.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        # If MFRC522 library not found, show warning
        if MFRC522 is None:
            self.label.config(text="MFRC522 library not found!\nPlace MFRC522.py in this folder.")
            return

        # Create MFRC522 reader
        self.reader = MFRC522.MFRC522()
        self.continue_reading = True

        # Start scanning in a background thread
        threading.Thread(target=self.scan_loop, daemon=True).start()

        # Run mainloop only if standalone
        if parent is None:
            self.root.mainloop()

    def log(self, text):
        self.log_box.config(state=tk.NORMAL)
        self.log_box.insert(tk.END, f"{text}\n")
        self.log_box.see(tk.END)
        self.log_box.config(state=tk.DISABLED)

    def uid_to_string(self, uid):
        return ''.join(format(x, '02X') for x in uid[::-1])

    def scan_loop(self):
        while self.continue_reading:
            (status, TagType) = self.reader.MFRC522_Request(self.reader.PICC_REQIDL)
            if status == self.reader.MI_OK:
                self.log("Card detected")
                (status, uid) = self.reader.MFRC522_SelectTagSN()
                if status == self.reader.MI_OK:
                    self.log(f"Card UID: {self.uid_to_string(uid)}")
                else:
                    self.log("Authentication error")
            time.sleep(0.5)

    def on_start(self):
        """Optional launcher hook"""
        self.log("RFID plugin started")
