#!/usr/bin/env python3
import os
import sys
from PyQt6.QtWidgets import (
    QWidget, QLabel, QCheckBox, QPushButton, QVBoxLayout, QHBoxLayout, QGridLayout, QApplication, QSpacerItem, QSizePolicy, QToolTip
)
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt, QTimer

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

        self.timer = QTimer()
        self.timer.timeout.connect(self.check_card)
        self.timer.start(500)

    def init_ui(self):
        main_layout = QVBoxLayout()
        self.setLayout(main_layout)

        # Logo at top-left
        self.logo_label = QLabel(self)
        logo_path = os.path.join(plugin_folder, "logo.png")
        if os.path.exists(logo_path):
            pixmap = QPixmap(logo_path).scaled(300, 75, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.logo_label.setPixmap(pixmap)
            self.logo_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        main_layout.addWidget(self.logo_label)

        # Optional background
        self.bg_label = QLabel(self)
        bg_path = os.path.join(plugin_folder, "background.png")
        if os.path.exists(bg_path):
            pixmap = QPixmap(bg_path).scaled(self.width(), self.height(), Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            self.bg_label.setPixmap(pixmap)
            self.bg_label.setGeometry(0, 0, self.width(), self.height())
            self.bg_label.lower()

        # Grid container
        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout()
        self.grid_widget.setLayout(self.grid_layout)
        self.grid_widget.setStyleSheet("background-color: rgba(0,0,0,100); border-radius: 10px;")
        main_layout.addWidget(self.grid_widget, alignment=Qt.AlignmentFlag.AlignHCenter)

        # Make checkboxes larger (3×)
        for i in range(ROWS):
            for j in range(COLUMNS):
                cb = QCheckBox("")
                cb.setStyleSheet("color: lightgrey; font-size: 18px; padding: 10px;")
                cb.stateChanged.connect(self.checkbox_clicked)
                self.grid_layout.addWidget(cb, i, j)
                self.checkboxes.append(cb)

        # Pagination buttons
        pagination_layout = QHBoxLayout()
        self.prev_button = QPushButton("Previous")
        self.prev_button.clicked.connect(self.prev_page)
        self.next_button = QPushButton("Next")
        self.next_button.clicked.connect(self.next_page)
        pagination_layout.addWidget(self.prev_button)
        pagination_layout.addWidget(self.next_button)
        main_layout.addLayout(pagination_layout)

        # Spacer at bottom
        main_layout.addItem(QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))

    def checkbox_clicked(self):
        cb = self.sender()
        if cb.text():
            QApplication.clipboard().setText(cb.text())
            QToolTip.showText(cb.mapToGlobal(cb.rect().center()), "Copied!", cb)
            QTimer.singleShot(1000, QToolTip.hideText)

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
                if page_cards[i] == highlight_uid:
                    cb.setStyleSheet("color: green; font-weight: bold; font-size: 18px; padding: 10px;")
                else:
                    cb.setStyleSheet("color: lightgrey; font-size: 18px; padding: 10px;")
                cb.setChecked(False)
                cb.setEnabled(True)
            else:
                cb.setText("")
                cb.setChecked(False)
                cb.setEnabled(False)

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
