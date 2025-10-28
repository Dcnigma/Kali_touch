#!/usr/bin/env python3
import os
import sys
import json
from PyQt6.QtWidgets import (
    QWidget, QLabel, QCheckBox, QPushButton, QVBoxLayout, QHBoxLayout, QGridLayout,
    QApplication, QSpacerItem, QSizePolicy, QToolTip
)
from PyQt6.QtGui import QPixmap, QColor
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

CARDS_PER_PAGE = 16  # 2 columns x 4 rows
COLUMNS = 2
ROWS = 4
ANIMATION_STEPS = 10
ANIMATION_INTERVAL = 50  # ms
CARDS_FILE = os.path.join(plugin_folder, "cards.json")  # file to store scanned UIDs

class MFRC522Plugin(QWidget):
    def __init__(self, parent=None, apps=None, cfg=None):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle("RFID Reader")
        self.setFixedSize(1150, 900)
        self.setMinimumSize(1150, 900)
        self.cards = self.load_cards()  # Load stored UIDs
        self.page = 0
        self.checkboxes = []
        self.continue_reading = True
        self.animations = {}  # uid -> current animation step

        self.init_ui()

        if LIB_AVAILABLE:
            self.reader = MFRC522.MFRC522()
        else:
            self.log_message(
                "MFRC522 Python library not available on this system.\nPlace MFRC522.py in the same folder as this plugin to read cards."
            )

        self.timer = QTimer()
        self.timer.timeout.connect(self.check_card)
        self.timer.start(500)

        # Animation timer
        self.anim_timer = QTimer()
        self.anim_timer.timeout.connect(self.update_animation)
        self.anim_timer.start(ANIMATION_INTERVAL)

        # Initial update to show loaded cards
        self.update_checkboxes()

    # --- Load/save UIDs ---
    def load_cards(self):
        if os.path.exists(CARDS_FILE):
            try:
                with open(CARDS_FILE, "r") as f:
                    return json.load(f)
            except Exception as e:
                self.log_message(f"Failed to load cards.json: {e}")
        return []

    def save_cards(self):
        try:
            with open(CARDS_FILE, "w") as f:
                json.dump(self.cards, f)
        except Exception as e:
            self.log_message(f"Failed to save cards.json: {e}")

    # --- UI setup ---
    def init_ui(self):
        main_layout = QVBoxLayout()
        self.setLayout(main_layout)

        # Logo
        self.logo_label = QLabel(self)
        logo_path = os.path.join(plugin_folder, "logo.png")
        if os.path.exists(logo_path):
            pixmap = QPixmap(logo_path).scaled(
                300, 75, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            self.logo_label.setPixmap(pixmap)
            self.logo_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        main_layout.addWidget(self.logo_label)

        # Grid container
        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout()
        self.grid_widget.setLayout(self.grid_layout)
        self.grid_widget.setStyleSheet("background-color: rgba(0,0,0,50); border-radius: 10px;")
        main_layout.addWidget(self.grid_widget, alignment=Qt.AlignmentFlag.AlignHCenter)

        for i in range(ROWS):
            for j in range(COLUMNS):
                cb = QCheckBox("")
                cb.setStyleSheet("color: lightgrey; font-size: 18px; padding: 10px;")
                cb.stateChanged.connect(self.checkbox_clicked)
                self.grid_layout.addWidget(cb, i, j)
                self.checkboxes.append(cb)

        # Pagination
        pagination_layout = QHBoxLayout()
        self.prev_button = QPushButton("Previous")
        self.prev_button.setFixedSize(80, 30)  # width=80px, height=30px
        self.prev_button.setStyleSheet("font-size: 12px; padding: 2px;")
        self.prev_button.clicked.connect(self.prev_page)
        self.next_button = QPushButton("Next")
        self.next_button.setFixedSize(80, 30)
        self.next_button.setStyleSheet("font-size: 12px; padding: 2px;")        
        self.next_button.clicked.connect(self.next_page)
        pagination_layout.addWidget(self.prev_button)
        pagination_layout.addWidget(self.next_button)
        main_layout.addLayout(pagination_layout)

        main_layout.addItem(QSpacerItem(20, 80, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))

    # --- Checkbox clicked ---
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

    # --- Check for new card ---
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
                    self.save_cards()  # persist new card
                self.animations[uid_str] = ANIMATION_STEPS  # trigger animation
                self.update_checkboxes(uid_str)

    # --- Update grid checkboxes ---
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
                # Initial color for stored cards
                if page_cards[i] not in self.animations:
                    cb.setStyleSheet("color: blue; font-size: 18px; padding: 10px;")
            else:
                cb.setText("")
                cb.setChecked(False)
                cb.setEnabled(False)

        # If highlighted UID is not on current page, switch page
        if highlight_uid and highlight_uid not in page_cards:
            index = self.cards.index(highlight_uid)
            self.page = index // CARDS_PER_PAGE
            self.update_checkboxes(highlight_uid)

    # --- Animate new scans ---
    def update_animation(self):
        for i, cb in enumerate(self.checkboxes):
            uid = cb.text()
            if uid in self.animations and self.animations[uid] > 0:
                step = self.animations[uid]
                green_value = int(255 * step / ANIMATION_STEPS)
                cb.setStyleSheet(f"color: rgb(0,{green_value},0); font-size: 18px; padding: 10px;")
                self.animations[uid] -= 1
            elif uid in self.animations and self.animations[uid] <= 0:
                cb.setStyleSheet("color: blue; font-size: 18px; padding: 10px;")
                del self.animations[uid]

    # --- Pagination ---
    def next_page(self):
        total_pages = max(1, (len(self.cards) + CARDS_PER_PAGE - 1) // CARDS_PER_PAGE)
        self.page = (self.page + 1) % total_pages
        self.update_checkboxes()

    def prev_page(self):
        total_pages = max(1, (len(self.cards) + CARDS_PER_PAGE - 1) // CARDS_PER_PAGE)
        self.page = (self.page - 1 + total_pages) % total_pages
        self.update_checkboxes()
