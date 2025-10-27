#!/usr/bin/env python3
import os
import sys
from PyQt6.QtWidgets import (
    QWidget, QLabel, QCheckBox, QPushButton, QVBoxLayout, QHBoxLayout, QGridLayout, QApplication
)
from PyQt6.QtGui import QPixmap, QColor
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QClipboard

# Ensure plugin folder is in sys.path
plugin_folder = os.path.dirname(os.path.abspath(__file__))
if plugin_folder not in sys.path:
    sys.path.insert(0, plugin_folder)

# Try to import MFRC522
try:
    import MFRC522
    LIB_AVAILABLE = True
except ImportError:
    LIB_AVAILABLE = False

CARDS_PER_PAGE = 16  # 2 columns x 8 rows
COLUMNS = 2
ROWS = 8
FLASH_DURATION_MS = 500

class MFRC522Plugin(QWidget):
    def __init__(self, parent=None, apps=None, cfg=None):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle("RFID Reader")
        self.setFixedSize(800, 900)
        self.cards = []
        self.page = 0
        self.checkboxes = []
        self.continue_reading = True

        self.init_ui()

        if LIB_AVAILABLE:
            self.reader = MFRC522.MFRC522()
        else:
            self.log_message("MFRC522 Python library not available on this system.\nPlace MFRC522.py in the same folder as this plugin to read cards.")

        # Timer to poll cards
        self.timer = QTimer()
        self.timer.timeout.connect(self.check_card)
        self.timer.start(500)

    def init_ui(self):
        main_layout = QVBoxLayout()
        main_layout.setSpacing(20)
        self.setLayout(main_layout)

        # Logo
        self.logo_label = QLabel(self)
        logo_path = os.path.join(plugin_folder, "logo.png")
        if os.path.exists(logo_path):
            pixmap = QPixmap(logo_path).scaled(200, 50, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.logo_label.setPixmap(pixmap)
            self.logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.logo_label)
        main_layout.addStretch(1)  # move grid higher

        # Checkbox grid
        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout()
        self.grid_widget.setLayout(self.grid_layout)
        main_layout.addWidget(self.grid_widget)

        for i in range(ROWS):
            for j in range(COLUMNS):
                cb = QCheckBox("")
                cb.setStyleSheet("color: lightgrey; font-size: 16px;")
                cb.stateChanged.connect(self.checkbox_clicked)
                self.grid_layout.addWidget(cb, i, j)
                self.checkboxes.append(cb)

        # Pagination buttons
        pagination_layout = QHBoxLayout()
        self.prev_button = QPushButton("Previous")
        self.prev_button.clicked.connect(self.prev_page)
        self.next_button = QPushButton("Next")
        self.next_button.clicked.connect(self.next_page)
        pagination_layout.addStretch(1)
        pagination_layout.addWidget(self.prev_button)
        pagination_layout.addWidget(self.next_button)
        pagination_layout.addStretch(1)
        main_layout.addLayout(pagination_layout)

        # Clipboard feedback
        self.feedback_label = QLabel("")
        self.feedback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.feedback_label)

    def checkbox_clicked(self):
        cb = self.sender()
        if cb.text():
            clipboard = QApplication.clipboard()
            clipboard.setText(cb.text())
            self.feedback_label.setText(f"Copied UID: {cb.text()}")
            QTimer.singleShot(1000, lambda: self.feedback_label.setText(""))  # clear after 1s

    def log_message(self, text):
        print(text)

    def uid_to_string(self, uid):
        return ''.join(format(i, '02X') for i in uid)

    def check_card(self):
        if not LIB_AVAILABLE:
            return

        status, tag_type = self.reader.MFRC522_Request(self.reader.PICC_REQIDL)
        if status == self.reader.MI_OK:
            status, uid = self.reader.MFRC522_SelectTagSN()
            if status == self.reader.MI_OK:
                uid_str = self.uid_to_string(uid)
                if uid_str not in self.cards:
                    self.cards.append(uid_str)
                self.update_checkboxes(uid_str)

    def update_checkboxes(self, highlight_uid=None):
        total_pages = max(1, (len(self.cards) + CARDS_PER_PAGE - 1) // CARDS_PER_PAGE)
        self.page = min(self.page, total_pages - 1)

        start_index = self.page * CARDS_PER_PAGE
        end_index = start_index + CARDS_PER_PAGE
        page_cards = self.cards[start_index:end_index]

        for i, cb in enumerate(self.checkboxes):
            if i < len(page_cards):
                cb.setText(page_cards[i])
                cb.setChecked(False)
                cb.setEnabled(True)
                if page_cards[i] == highlight_uid:
                    # Flash animation
                    cb.setStyleSheet("color: green; font-weight: bold; font-size: 16px;")
                    QTimer.singleShot(FLASH_DURATION_MS, lambda cb=cb: cb.setStyleSheet("color: lightgrey; font-size: 16px;"))
                else:
                    cb.setStyleSheet("color: lightgrey; font-size: 16px;")
            else:
                cb.setText("")
                cb.setChecked(False)
                cb.setEnabled(False)

        # If highlighted UID is not on current page, switch page
        if highlight_uid and highlight_uid not in page_cards:
            index = self.cards.index(highlight_uid)
            self.page = index // CARDS_PER_PAGE
            self.update_checkboxes(highlight_uid)

    def next_page(self):
        total_pages = max(1, (len(self.cards) + CARDS_PER_PAGE - 1) // CARDS_PER_PAGE)
        self.page = (self.page + 1) % total_pages
        self.update_checkboxes()

    def prev_page(self):
        total_pages = max(1, (len(self.cards) + CARDS_PER_PAGE - 1) // CARDS_PER_PAGE)
        self.page = (self.page - 1 + total_pages) % total_pages
        self.update_checkboxes()
