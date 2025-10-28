import sys
import json
import os
import random
from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QGridLayout, QPushButton,
    QGraphicsOpacityEffect, QPropertyAnimation, QStackedLayout
)
from PyQt6.QtCore import Qt, QTimer, QSequentialAnimationGroup
from PyQt6.QtGui import QPixmap, QClipboard, QGuiApplication

CARDS_FILE = "cards.json"

class RFIDPlugin(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RFID Plugin")
        self.setFixedSize(1000, 800)

        # --- Load saved cards ---
        self.cards = self.load_cards()

        # --- Background setup ---
        self.setStyleSheet("""
            QWidget {
                background-image: url('background.png');
                background-repeat: no-repeat;
                background-position: center;
                background-size: cover;
            }
        """)

        # --- Main layout ---
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        # --- Logo ---
        self.logo = QLabel()
        pixmap = QPixmap("logo.png")
        self.logo.setPixmap(pixmap)
        self.logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.logo)

        # --- White space under logo ---
        spacer = QLabel("")
        spacer.setFixedHeight(20)
        layout.addWidget(spacer)

        # --- Container for grid ---
        self.grid_container = QWidget()
        self.grid_container.setStyleSheet("""
            QWidget {
                background-color: rgba(0, 0, 0, 50);
                border-radius: 10px;
            }
        """)
        layout.addWidget(self.grid_container, alignment=Qt.AlignmentFlag.AlignCenter)

        # --- Grid for UIDs ---
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setContentsMargins(30, 30, 30, 30)
        self.grid_layout.setSpacing(15)

        self.uid_buttons = []
        self.uids_per_page = 8
        self.current_page = 0

        # Create 2x4 grid (8 checkboxes)
        for i in range(8):
            btn = QPushButton("Empty")
            btn.setCheckable(True)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: rgba(255,255,255,100);
                    color: lightgray;
                    border: 1px solid gray;
                    border-radius: 6px;
                    padding: 8px;
                    font-size: 14px;
                }
                QPushButton:checked {
                    background-color: rgba(0,255,0,80);
                    color: white;
                }
            """)
            btn.clicked.connect(lambda _, b=btn: self.copy_uid(b))
            self.uid_buttons.append(btn)
            row, col = divmod(i, 2)
            self.grid_layout.addWidget(btn, row, col)

        # --- Navigation buttons ---
        nav_layout = QGridLayout()
        self.prev_button = QPushButton("⟨ Prev")
        self.next_button = QPushButton("Next ⟩")

        for btn in (self.prev_button, self.next_button):
            btn.setFixedWidth(120)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: rgba(255,255,255,100);
                    border: 1px solid gray;
                    border-radius: 8px;
                    font-weight: bold;
                    padding: 6px;
                }
                QPushButton:hover {
                    background-color: rgba(255,255,255,150);
                }
            """)

        self.prev_button.clicked.connect(self.prev_page)
        self.next_button.clicked.connect(self.next_page)
        nav_layout.addWidget(self.prev_button, 0, 0)
        nav_layout.addWidget(self.next_button, 0, 1)
        layout.addLayout(nav_layout)

        self.update_grid()

        # --- Simulated card reading (for demo) ---
        self.timer = QTimer()
        self.timer.timeout.connect(self.simulate_card)
        self.timer.start(5000)

        # --- Animations ---
        self.apply_fade_in_animations()

    # ===================================================
    #                 ANIMATIONS
    # ===================================================
    def apply_fade_in_animations(self):
        # Logo fade
        self.logo_effect = QGraphicsOpacityEffect()
        self.logo.setGraphicsEffect(self.logo_effect)
        logo_anim = QPropertyAnimation(self.logo_effect, b"opacity")
        logo_anim.setDuration(1000)
        logo_anim.setStartValue(0)
        logo_anim.setEndValue(1)

        # Grid fade
        self.grid_effect = QGraphicsOpacityEffect()
        self.grid_container.setGraphicsEffect(self.grid_effect)
        grid_anim = QPropertyAnimation(self.grid_effect, b"opacity")
        grid_anim.setDuration(1000)
        grid_anim.setStartValue(0)
        grid_anim.setEndValue(1)

        # Sequential fade: logo then grid
        seq = QSequentialAnimationGroup()
        seq.addAnimation(logo_anim)
        seq.addAnimation(grid_anim)
        seq.start()

    # ===================================================
    #               CARD SIMULATION
    # ===================================================
    def simulate_card(self):
        uid = f"UID-{random.randint(10000, 99999)}"
        if uid not in self.cards:
            self.cards.append(uid)
            self.save_cards()
        self.highlight_uid(uid)

    def highlight_uid(self, uid):
        total = len(self.cards)
        page = total // self.uids_per_page
        self.current_page = page
        self.update_grid()

        index = self.cards.index(uid) % self.uids_per_page
        if 0 <= index < len(self.uid_buttons):
            btn = self.uid_buttons[index]
            btn.setChecked(True)
            btn.setStyleSheet(btn.styleSheet().replace("lightgray", "white"))

    # ===================================================
    #                 PAGE NAVIGATION
    # ===================================================
    def update_grid(self):
        start = self.current_page * self.uids_per_page
        end = start + self.uids_per_page
        page_cards = self.cards[start:end]

        for i, btn in enumerate(self.uid_buttons):
            if i < len(page_cards):
                btn.setText(page_cards[i])
                btn.setChecked(False)
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: rgba(255,255,255,100);
                        color: lightgray;
                        border: 1px solid gray;
                        border-radius: 6px;
                        padding: 8px;
                        font-size: 14px;
                    }
                    QPushButton:checked {
                        background-color: rgba(0,255,0,80);
                        color: white;
                    }
                """)
            else:
                btn.setText("Empty")
                btn.setChecked(False)

    def next_page(self):
        if (self.current_page + 1) * self.uids_per_page < len(self.cards):
            self.current_page += 1
            self.update_grid()

    def prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self.update_grid()

    # ===================================================
    #                   CLIPBOARD
    # ===================================================
    def copy_uid(self, button):
        uid = button.text()
        if uid and uid != "Empty":
            clipboard: QClipboard = QGuiApplication.clipboard()
            clipboard.setText(uid)
            button.setStyleSheet(button.styleSheet().replace("rgba(255,255,255,100)", "rgba(0,255,0,80)"))
            print(f"Copied UID: {uid}")

    # ===================================================
    #                   SAVE / LOAD
    # ===================================================
    def save_cards(self):
        with open(CARDS_FILE, "w") as f:
            json.dump(self.cards, f, indent=4)

    def load_cards(self):
        if os.path.exists(CARDS_FILE):
            with open(CARDS_FILE, "r") as f:
                return json.load(f)
        return []

# ===================================================
#                    MAIN
# ===================================================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = RFIDPlugin()
    window.show()
    sys.exit(app.exec())
