# plugins/plugin_base.py
from PyQt6.QtWidgets import QWidget

class PluginBase(QWidget):
    """Optional base class for plugins. Plugins can inherit from this."""
    name = "PluginBase"
    def __init__(self, parent=None):
        super().__init__(parent)

    def on_open(self):
        """Called when plugin is presented."""
        pass

    def on_close(self):
        """Called when plugin is closed."""
        pass
