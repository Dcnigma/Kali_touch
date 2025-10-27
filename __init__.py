# spacer to push bottom bar to bottom
# ui_layout.addItem(QSpacerItem(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))
ui_layout.addStretch(1)
self.apps = apps  # in __init__
self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
# ensure close button exists (created detached from launcher window)
self.close_btn = None
self.ensure_close_btn()
self.show()
self.raise_()
self.activateWindow()
