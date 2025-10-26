# spacer to push bottom bar to bottom
# ui_layout.addItem(QSpacerItem(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))
ui_layout.addStretch(1)
self.apps = apps  # in __init__
self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
self.show()
self.raise_()
self.activateWindow()
