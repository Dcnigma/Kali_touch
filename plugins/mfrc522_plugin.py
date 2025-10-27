from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QGridLayout, QCheckBox, QLabel, QSpacerItem, QSizePolicy, QToolTip
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap, QClipboard
import os

ROWS, COLUMNS = 8, 2

class RFIDUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RFID Reader")
        self.resize(800, 900)

        self.checkboxes = []
        self.uids = [""] * (ROWS * COLUMNS)  # dummy UID list

        main_layout = QVBoxLayout(self)

        # Top spacer
        main_layout.addItem(QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))

        # Logo
        self.logo_label = QLabel(self)
        logo_path = "logo.png"  # place logo.png in same folder
        if os.path.exists(logo_path):
            pixmap = QPixmap(logo_path).scaled(200, 50, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.logo_label.setPixmap(pixmap)
            self.logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.logo_label, alignment=Qt.AlignmentFlag.AlignHCenter)

        # Grid widget
        self.grid_widget = QWidget()
        self.grid_widget.setStyleSheet("background-color: rgba(0,0,0,80); border-radius: 10px;")
        self.grid_layout = QGridLayout()
        self.grid_layout.setSpacing(10)
        self.grid_widget.setLayout(self.grid_layout)
        main_layout.addWidget(self.grid_widget, alignment=Qt.AlignmentFlag.AlignHCenter)

        for i in range(ROWS):
            for j in range(COLUMNS):
                idx = i * COLUMNS + j
                cb = QCheckBox("")
                cb.setStyleSheet("color: lightgrey; font-size: 16px;")
                cb.uid_index = idx
                cb.stateChanged.connect(self.checkbox_clicked)
                self.grid_layout.addWidget(cb, i, j)
                self.checkboxes.append(cb)

        # Bottom spacer
        main_layout.addItem(QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))

    def checkbox_clicked(self, state):
        sender = self.sender()
        uid = self.uids[sender.uid_index]
        if uid:
            QApplication.clipboard().setText(uid)
            # Show temporary tooltip
            QToolTip.showText(sender.mapToGlobal(sender.rect().center()), "Copied!", sender)
            QTimer.singleShot(1000, QToolTip.hideText)  # hide after 1 second

    # Example function to mark UID as scanned
    def mark_uid(self, uid):
        if uid not in self.uids:
            try:
                idx = self.uids.index("")
            except ValueError:
                idx = 0  # overwrite oldest if full
            self.uids[idx] = uid
        else:
            idx = self.uids.index(uid)

        # Update checkbox colors
        for i, cb in enumerate(self.checkboxes):
            if i < len(self.uids) and self.uids[i] == uid:
                cb.setStyleSheet("color: green; font-size: 16px;")
                # Optionally move to page if using pages
            else:
                cb.setStyleSheet("color: lightgrey; font-size: 16px;")
