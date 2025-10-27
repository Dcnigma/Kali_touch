# spacer to push bottom bar to bottom
# ui_layout.addItem(QSpacerItem(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))
ui_layout.addStretch(1)
self.apps = apps  # in __init__
self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
self.close_btn = FloatingCloseButton(self.close_current)
self.close_btn.hide()
self._position_close_btn()
self.show()
self.raise_()
self.activateWindow()
