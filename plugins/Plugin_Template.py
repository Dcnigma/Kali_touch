#!/usr/bin/env python3
import os
import sys
import json
import socket
from PyQt6.QtWidgets import (
    QWidget, QLabel, QCheckBox, QPushButton, QVBoxLayout, QHBoxLayout,
    QGridLayout, QApplication, QSpacerItem, QSizePolicy
)
from PyQt6.QtGui import QPixmap, QPalette, QBrush
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve

plugin_folder = os.path.dirname(os.path.abspath(__file__))
if plugin_folder not in sys.path:
    sys.path.insert(0, plugin_folder)

CARDS_FILE = os.path.join(plugin_folder, "data.json")
COLUMNS = 2
ROWS = 4
CARDS_PER_PAGE = COLUMNS * ROWS


class PluginTemplate(QWidget):
    def __init__(self, parent=None, cfg=None):
        super().__init__(parent)
        self.cfg = cfg

        self.page = 0
        self.checkboxes = []
        self.cards = []
        self.last_action = None

        self.setFixedSize(1015, 570)
        self.move(-50, 0)
        self.setWindowTitle("Plugin Template")

        # Background
        bg_path = os.path.join(plugin_folder, "background.png")
        if os.path.exists(bg_path):
            pixmap = QPixmap(bg_path).scaled(
                self.size(), Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            palette = self.palette()
            palette.setBrush(QPalette.ColorRole.Window, QBrush(pixmap))
            self.setAutoFillBackground(True)
            self.setPalette(palette)

        # Load JSON data
        self.load_data()

        # Initialize UI
        self.init_ui()

        # Timer for periodic updates
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_ui)
        self.timer.start(500)

        # Fade-in animation for grid
        self.grid_widget.setWindowOpacity(0.0)
        self.fade_in_animation = QPropertyAnimation(self.grid_widget, b"windowOpacity")
        self.fade_in_animation.setDuration(1500)
        self.fade_in_animation.setStartValue(0.0)
        self.fade_in_animation.setEndValue(1.0)
        self.fade_in_animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        QTimer.singleShot(500, self.fade_in_animation.start)

    # ---------------------- UI ----------------------
    def init_ui(self):
        main_layout = QVBoxLayout()
        self.setLayout(main_layout)

        spacer_top = QWidget()
        spacer_top.setFixedHeight(10)
        main_layout.addWidget(spacer_top)

        # Logo
        self.logo_label = QLabel(self)
        logo_path = os.path.join(plugin_folder, "logo.png")
        if os.path.exists(logo_path):
            pixmap = QPixmap(logo_path).scaled(
                200, 50, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.logo_label.setPixmap(pixmap)
            self.logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignTop)
        main_layout.addWidget(self.logo_label, alignment=Qt.AlignmentFlag.AlignCenter)

        spacer_logo = QWidget()
        spacer_logo.setFixedHeight(20)
        main_layout.addWidget(spacer_logo)

        # Grid container
        self.grid_widget = QWidget()
        self.grid_widget.setFixedSize(500, 320)
        self.grid_layout = QGridLayout()
        self.grid_widget.setLayout(self.grid_layout)
        self.grid_widget.setStyleSheet("background-color: rgba(0,0,0,120); border-radius: 10px;")
        main_layout.addWidget(self.grid_widget, alignment=Qt.AlignmentFlag.AlignCenter)

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

        # Info label
        self.info_label = QLabel("No action yet.", self)
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.info_label.setStyleSheet("color: lightgrey; font-size: 16px;")
        main_layout.addWidget(self.info_label)

        main_layout.addItem(QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))

        self.update_checkboxes()

    # ---------------------- Checkbox click ----------------------
    def checkbox_clicked(self):
        cb = self.sender()
        if cb.text():
            self.info_label.setText(f"Clicked: {cb.text()}")
            self.last_action = cb.text()
            self.send_unix_message({"type": "user_good", "data": cb.text()})
            self.save_data()

    # ---------------------- Pagination ----------------------
    def next_page(self):
        total_pages = max(1, (len(self.cards) + CARDS_PER_PAGE - 1) // CARDS_PER_PAGE)
        self.page = (self.page + 1) % total_pages
        self.update_checkboxes()

    def prev_page(self):
        total_pages = max(1, (len(self.cards) + CARDS_PER_PAGE - 1) // CARDS_PER_PAGE)
        self.page = (self.page - 1 + total_pages) % total_pages
        self.update_checkboxes()

    # ---------------------- Update UI ----------------------
    def update_ui(self):
        pass  # Placeholder for periodic updates

    # ---------------------- Checkboxes ----------------------
    def update_checkboxes(self):
        start_index = self.page * CARDS_PER_PAGE
        end_index = start_index + CARDS_PER_PAGE
        page_cards = self.cards[start_index:end_index]

        for i, cb in enumerate(self.checkboxes):
            if i < len(page_cards):
                cb.setText(page_cards[i])
                cb.setEnabled(True)
            else:
                cb.setText("")
                cb.setEnabled(False)

    # ---------------------- JSON handling ----------------------
    def save_data(self):
        try:
            data = {"cards": self.cards, "last_action": self.last_action}
            with open(CARDS_FILE, "w") as f:
                json.dump(data, f)
        except Exception as e:
            print(f"Error saving data: {e}")

    def load_data(self):
        if os.path.exists(CARDS_FILE):
            try:
                with open(CARDS_FILE, "r") as f:
                    data = json.load(f)
                    self.cards = data.get("cards", [])
                    self.last_action = data.get("last_action", None)
            except Exception as e:
                print(f"Error loading data: {e}")
                self.cards = []
                self.last_action = None
        else:
            self.cards = []

    # ---------------------- Unix socket ----------------------
    def send_unix_message(self, msg: dict):
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
            sock.sendto(json.dumps(msg).encode(), "/tmp/rebecca.sock")
            sock.close()
        except Exception as e:
            print(f"Error sending socket message: {e}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = PluginTemplate()
    window.show()
    sys.exit(app.exec())
