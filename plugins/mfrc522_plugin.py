#!/usr/bin/env python3
import os
import sys
import json
from PyQt6.QtWidgets import (
    QWidget, QLabel, QCheckBox, QPushButton, QVBoxLayout, QHBoxLayout,
    QGridLayout, QApplication, QSpacerItem, QSizePolicy, QToolTip
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

CARDS_PER_PAGE = 8  # 2 columns x 8 rows
COLUMNS = 2
ROWS = 4
ANIMATION_STEPS = 10
ANIMATION_INTERVAL = 50  # ms
CARDS_FILE = os.path.join(plugin_folder, "cards.json")


class MFRC522Plugin(QWidget):
    def __init__(self, parent=None, apps=None, cfg=None):
        super().__init__(parent)
        self.cfg = cfg

        # Window size and position
        self.setFixedSize(1015, 500)
        self.move(-50, 0)
        self.setWindowTitle("RFID Reader")

        self.cards = []
        self.page = 0
        self.checkboxes = []
        self.animations = {}  # uid -> current animation step

        self.load_cards()
        self.init_ui()

        if LIB_AVAILABLE:
            self.reader = MFRC522.MFRC522()
        else:
            self.log_message("MFRC522 Python library not available on this system.\nPlace MFRC522.py in the same folder as this plugin to read cards.")

        # Timer to poll cards
        self.timer = QTimer()
        self.timer.timeout.connect(self.check_card)
        self.timer.start(500)

        # Animation timer
        self.anim_timer = QTimer()
        self.anim_timer.timeout.connect(self.update_animation)
        self.anim_timer.start(ANIMATION_INTERVAL)

    # ---------------------- UI ----------------------
    def init_ui(self):
        main_layout = QVBoxLayout()
        self.setLayout(main_layout)
        # Spacer between logo and grid
        spacer = QWidget()
        spacer.setFixedHeight(20)  # 20 pixels of space
        main_layout.addWidget(spacer)
        # Logo top-left
        self.logo_label = QLabel(self)
        logo_path = os.path.join(plugin_folder, "logo.png")
        if os.path.exists(logo_path):
            pixmap = QPixmap(logo_path).scaled(200, 50, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.logo_label.setPixmap(pixmap)
            self.logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignTop)
        main_layout.addWidget(self.logo_label, alignment=Qt.AlignmentFlag.AlignCenter)

        # Spacer between logo and grid
        spacer = QWidget()
        spacer.setFixedHeight(20)  # 20 pixels of space
        main_layout.addWidget(spacer)
        
        # Grid container
        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout()
        self.grid_widget.setLayout(self.grid_layout)
        self.grid_widget.setStyleSheet("background-color: rgba(0,0,0,50); border-radius: 10px;")
        main_layout.addWidget(self.grid_widget, alignment=Qt.AlignmentFlag.AlignHCenter)

        # Checkboxes
        for i in range(ROWS):
            for j in range(COLUMNS):
                cb = QCheckBox("")
                cb.setStyleSheet("color: lightgrey; font-size: 22px; padding: 20px;")
                cb.stateChanged.connect(self.checkbox_clicked)
                self.grid_layout.addWidget(cb, i, j)
                self.checkboxes.append(cb)

        # Pagination buttons
        pagination_layout = QHBoxLayout()
        self.prev_button = QPushButton("Previous")
        self.prev_button.setFixedSize(100, 35)
        self.prev_button.clicked.connect(self.prev_page)
        self.next_button = QPushButton("Next")
        self.next_button.setFixedSize(100, 35)
        self.next_button.clicked.connect(self.next_page)
        pagination_layout.addWidget(self.prev_button)
        pagination_layout.addWidget(self.next_button)
        main_layout.addLayout(pagination_layout)

        main_layout.addItem(QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))

        self.update_checkboxes()  # show saved cards

    # ---------------------- Checkbox click ----------------------
    def checkbox_clicked(self):
        cb = self.sender()
        if cb.text():
            QApplication.clipboard().setText(cb.text())
            QToolTip.showText(cb.mapToGlobal(cb.rect().center()), "Copied!", cb)
            QTimer.singleShot(1000, QToolTip.hideText)

    # ---------------------- Logging ----------------------
    def log_message(self, text):
        print(text)

    # ---------------------- UID helpers ----------------------
    def uid_to_string(self, uid):
        return ''.join(format(i, '02X') for i in uid)

    # ---------------------- Card reading ----------------------
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
                    self.save_cards()
                self.animations[uid_str] = ANIMATION_STEPS
                # Auto-switch to correct page if needed
                self.goto_page_for_uid(uid_str)

    # ---------------------- Pagination & display ----------------------
    def goto_page_for_uid(self, uid_str):
        index = self.cards.index(uid_str)
        new_page = index // CARDS_PER_PAGE
        if new_page != self.page:
            self.page = new_page
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
            else:
                cb.setText("")
                cb.setChecked(False)
                cb.setEnabled(False)

        if highlight_uid and highlight_uid not in page_cards:
            self.goto_page_for_uid(highlight_uid)

    def update_animation(self):
        for i, cb in enumerate(self.checkboxes):
            uid = cb.text()
            if uid in self.animations and self.animations[uid] > 0:
                step = self.animations[uid]
                green_value = int(255 * step / ANIMATION_STEPS)
                cb.setStyleSheet(f"color: rgb(0,{green_value},0); font-size: 20px; padding: 15px;")
                self.animations[uid] -= 1
            elif uid in self.animations and self.animations[uid] <= 0:
                cb.setStyleSheet("color: lightgrey; font-size: 20px; padding: 15px;")
                del self.animations[uid]

    # ---------------------- Pagination buttons ----------------------
    def next_page(self):
        total_pages = max(1, (len(self.cards) + CARDS_PER_PAGE - 1) // CARDS_PER_PAGE)
        self.page = (self.page + 1) % total_pages
        self.update_checkboxes()

    def prev_page(self):
        total_pages = max(1, (len(self.cards) + CARDS_PER_PAGE - 1) // CARDS_PER_PAGE)
        self.page = (self.page - 1 + total_pages) % total_pages
        self.update_checkboxes()

    # ---------------------- Save/load cards ----------------------
    def save_cards(self):
        try:
            with open(CARDS_FILE, "w") as f:
                json.dump(self.cards, f)
        except Exception as e:
            self.log_message(f"Error saving cards: {e}")

    def load_cards(self):
        if os.path.exists(CARDS_FILE):
            try:
                with open(CARDS_FILE, "r") as f:
                    self.cards = json.load(f)
            except Exception as e:
                self.log_message(f"Error loading cards: {e}")
                self.cards = []
