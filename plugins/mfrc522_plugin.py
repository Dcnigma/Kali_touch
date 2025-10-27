#!/usr/bin/env python3
import os
import sys
import time
import threading
try:
    from MFRC522 import MFRC522
except ImportError:
    print("MFRC522 Python library not available on this system.")
    print("Place MFRC522.py in the same folder as this plugin to read cards.")
    MFRC522 = None

if MFRC522:
    import tkinter as tk
    from tkinter import ttk

    class RFIDReaderUI:
        def __init__(self, master):
            self.master = master
            self.master.title("MFRC522 RFID Reader")
            self.master.geometry("800x900")

            self.label = tk.Label(master, text="Scan a card...", font=("Helvetica", 24))
            self.label.pack(pady=40)

            self.log_frame = tk.Frame(master)
            self.log_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

            self.log_box = tk.Text(self.log_frame, state=tk.DISABLED, font=("Courier", 14))
            self.log_box.pack(fill=tk.BOTH, expand=True)

            self.reader = MFRC522()
            self.continue_reading = True

            # Start scanning in a separate thread
            threading.Thread(target=self.scan_loop, daemon=True).start()

        def uidToString(self, uid):
            return ''.join(format(x, '02X') for x in uid)

        def log(self, text):
            self.log_box.config(state=tk.NORMAL)
            self.log_box.insert(tk.END, f"{time.strftime('%H:%M:%S')} - {text}\n")
            self.log_box.see(tk.END)
            self.log_box.config(state=tk.DISABLED)

        def scan_loop(self):
            while self.continue_reading:
                status, _ = self.reader.MFRC522_Request(self.reader.PICC_REQIDL)
                if status == self.reader.MI_OK:
                    status, uid = self.reader.MFRC522_SelectTagSN()
                    if status == self.reader.MI_OK:
                        uid_str = self.uidToString(uid)
                        self.master.after(0, self.update_ui, uid_str)
                time.sleep(0.1)

        def update_ui(self, uid_str):
            self.label.config(text=f"Card UID: {uid_str}")
            self.log(f"Card read: {uid_str}")

    if __name__ == "__main__":
        root = tk.Tk()
        app = RFIDReaderUI(root)
        root.mainloop()
