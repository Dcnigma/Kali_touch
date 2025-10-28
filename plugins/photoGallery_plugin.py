#!/usr/bin/env python3
"""
photoGallery_plugin.py
Touch-friendly photo gallery + editor for Raspberry Pi touchscreen.
"""

import os
import sys
import uuid
from datetime import datetime
from functools import partial
from PIL import Image, ImageOps, ImageQt, ImageDraw, ImageFont
from PyQt6.QtWidgets import (
    QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QGridLayout,
    QApplication, QScrollArea, QFileDialog, QMessageBox, QDialog, QComboBox,
    QSpinBox, QColorDialog, QLineEdit, QFrame
)
from PyQt6.QtGui import QPixmap, QImage, QColor
from PyQt6.QtCore import Qt, QSize, pyqtSignal, QTimer, QPoint

# ---------------- Configuration ----------------
plugin_folder = os.path.dirname(os.path.abspath(__file__))
PHOTO_FOLDER = os.path.join(plugin_folder, "/home/kali/Pictures/SavedPictures")

THUMBNAIL_SIZE = (180, 120)
WINDOW_WIDTH = 1015
WINDOW_HEIGHT = 550
SUPPORTED_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".gif")
TOOLBAR_HIDE_MS = 4000


# ---------------- Helper ----------------
def pil_to_qpixmap(img: Image.Image) -> QPixmap:
    if img.mode not in ("RGBA", "RGB"):
        img = img.convert("RGBA")
    qt_img = ImageQt.ImageQt(img)
    return QPixmap.fromImage(QImage(qt_img))


def ensure_folder():
    os.makedirs(PHOTO_FOLDER, exist_ok=True)


# ---------------- Clickable Label ----------------
class ClickableLabel(QLabel):
    clicked = pyqtSignal()

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()


# ---------------- Image Editor ----------------
class ImageEditorDialog(QDialog):
    def __init__(self, image_path, parent=None, on_saved_callback=None):
        super().__init__(parent)
        self.image_path = image_path
        self.on_saved_callback = on_saved_callback
        self.setFixedSize(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.move(0, 0)

        self.base_image = Image.open(self.image_path).convert("RGBA")
        self.working = self.base_image.copy()
        self.layers = []
        self.selected_layer_id = None
        self.dragging = False
        self.drag_offset = (0, 0)

        self.default_text_color = (255, 255, 255, 255)
        self.default_fill = (0, 0, 0, 0)
        self.default_stroke = (255, 0, 0, 255)

        self.init_ui()
        self.update_display()

        # Auto-hide toolbar
        self.hide_timer = QTimer(self)
        self.hide_timer.setInterval(TOOLBAR_HIDE_MS)
        self.hide_timer.timeout.connect(self.hide_toolbar)
        self.reset_hide_timer()

    def init_ui(self):
        self.setWindowTitle(os.path.basename(self.image_path))
        layout = QVBoxLayout(self)
        self.setLayout(layout)

        # Image display
        self.image_label = QLabel(self)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("background-color: black;")
        layout.addWidget(self.image_label, 1)

        # Back button
        self.back_btn = QPushButton("← Back to Gallery", self)
        self.back_btn.setStyleSheet("background: rgba(40,40,40,200); color: white; padding:6px; border-radius:6px;")
        self.back_btn.setFixedHeight(36)
        self.back_btn.move(12, 12)
        self.back_btn.clicked.connect(self.close)
        self.back_btn.show()

        # Toolbar
        self.toolbar = QFrame(self)
        self.toolbar.setStyleSheet("background-color: rgba(30,30,30,220);")
        tb = QHBoxLayout(self.toolbar)
        self.toolbar.setFixedHeight(110)
        layout.addWidget(self.toolbar)

        # --- Transform buttons ---
        for txt, fn in [("Rotate 90°", self.rotate90),
                        ("Negative", self.negative),
                        ("Black & White", self.blackwhite)]:
            b = QPushButton(txt)
            b.clicked.connect(fn)
            tb.addWidget(b)

        # --- Text tools ---
        tb.addWidget(QLabel("Text:"))
        self.text_input = QLineEdit()
        self.text_input.setPlaceholderText("Enter text")
        tb.addWidget(self.text_input)
        self.font_spin = QSpinBox()
        self.font_spin.setRange(8, 200)
        self.font_spin.setValue(24)
        tb.addWidget(self.font_spin)

        btn_text_color = QPushButton("Text Color")
        btn_text_color.clicked.connect(self.choose_text_color)
        tb.addWidget(btn_text_color)

        btn_add_text = QPushButton("Add Text")
        btn_add_text.clicked.connect(self.add_text_layer)
        tb.addWidget(btn_add_text)

        # --- Shape tools ---
        tb.addWidget(QLabel("Shape:"))
        self.shape_combo = QComboBox()
        self.shape_combo.addItems(["None", "Rectangle", "Ellipse", "Line"])
        tb.addWidget(self.shape_combo)

        self.stroke_spin = QSpinBox()
        self.stroke_spin.setRange(1, 50)
        self.stroke_spin.setValue(3)
        tb.addWidget(QLabel("Stroke"))
        tb.addWidget(self.stroke_spin)

        btn_fill_color = QPushButton("Fill Color")
        btn_fill_color.clicked.connect(self.choose_fill_color)
        tb.addWidget(btn_fill_color)

        btn_stroke_color = QPushButton("Stroke Color")
        btn_stroke_color.clicked.connect(self.choose_stroke_color)
        tb.addWidget(btn_stroke_color)

        btn_add_shape = QPushButton("Add Shape")
        btn_add_shape.clicked.connect(self.add_shape_layer)
        tb.addWidget(btn_add_shape)

        # --- Save buttons ---
        btn_save = QPushButton("💾 Save (overwrite)")
        btn_save.clicked.connect(self.save_overwrite)
        tb.addWidget(btn_save)
        btn_save_new = QPushButton("🆕 Save As New")
        btn_save_new.clicked.connect(self.save_as_new)
        tb.addWidget(btn_save_new)

        # Info label
        self.info_label = QLabel("")
        self.info_label.setStyleSheet("color: white;")
        tb.addWidget(self.info_label)

        # Mouse control
        self.image_label.mousePressEvent = self._img_mouse_press
        self.image_label.mouseMoveEvent = self._img_mouse_move
        self.image_label.mouseReleaseEvent = self._img_mouse_release

    # ---------- Toolbar visibility ----------
    def reset_hide_timer(self):
        self.toolbar.show()
        self.hide_timer.start()

    def hide_toolbar(self):
        self.toolbar.hide()

    def mouseMoveEvent(self, ev):
        self.reset_hide_timer()
        return super().mouseMoveEvent(ev)

    def keyPressEvent(self, ev):
        self.reset_hide_timer()
        if ev.key() == Qt.Key.Key_Escape:
            self.close()
        return super().keyPressEvent(ev)

    # ---------- Utility ----------
    def _get_layer(self, lid):
        for L in self.layers:
            if L["id"] == lid:
                return L
        return None

    # ---------- Image Display ----------
    def update_display(self):
        canvas = self.working.copy()
        draw = ImageDraw.Draw(canvas)
        for L in self.layers:
            if L["type"] == "text":
                fnt = ImageFont.truetype("DejaVuSans.ttf", L["font_size"])
                bbox = draw.textbbox((L["x"], L["y"]), L["text"], font=fnt)
                tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
                draw.text((L["x"] - tw // 2, L["y"] - th // 2), L["text"], font=fnt, fill=L["color"])
            elif L["type"] == "shape":
                x1, y1, x2, y2 = L["bbox"]
                stroke = L["stroke"]
                stroke_col = L["stroke_color"]
                fill = L["fill_color"]
                s = L["shape"]
                if s == "rectangle":
                    if fill and fill[3] != 0:
                        draw.rectangle([x1, y1, x2, y2], fill=tuple(fill))
                    draw.rectangle([x1, y1, x2, y2], outline=tuple(stroke_col), width=stroke)
                elif s == "ellipse":
                    if fill and fill[3] != 0:
                        draw.ellipse([x1, y1, x2, y2], fill=tuple(fill))
                    draw.ellipse([x1, y1, x2, y2], outline=tuple(stroke_col), width=stroke)
                elif s == "line":
                    draw.line([x1, y1, x2, y2], fill=tuple(stroke_col), width=stroke)

        qpix = pil_to_qpixmap(canvas)
        scaled = qpix.scaled(WINDOW_WIDTH, WINDOW_HEIGHT - 120, Qt.AspectRatioMode.KeepAspectRatio)
        self.image_label.setPixmap(scaled)

    # ---------- Layer creation ----------
    def add_text_layer(self):
        t = self.text_input.text().strip()
        if not t:
            QMessageBox.information(self, "Text", "Enter text first.")
            return
        w, h = self.working.size
        L = {"id": uuid.uuid4().hex, "type": "text", "text": t, "font_size": self.font_spin.value(),
             "color": self.default_text_color, "x": w // 2, "y": h // 2}
        self.layers.append(L)
        self.selected_layer_id = L["id"]
        self.update_display()

    def add_shape_layer(self):
        s = self.shape_combo.currentText().lower()
        if s == "none":
            QMessageBox.information(self, "Shape", "Select a shape first.")
            return
        w, h = self.working.size
        m = min(w, h) // 6
        L = {"id": uuid.uuid4().hex, "type": "shape", "shape": s,
             "bbox": (w // 2 - m, h // 2 - m, w // 2 + m, h // 2 + m),
             "stroke": self.stroke_spin.value(),
             "stroke_color": self.default_stroke,
             "fill_color": self.default_fill}
        self.layers.append(L)
        self.selected_layer_id = L["id"]
        self.update_display()

    # ---------- Mouse actions ----------
    def _img_mouse_press(self, ev):
        self.reset_hide_timer()
        if ev.button() != Qt.MouseButton.LeftButton:
            return
        self.dragging = True
        self.drag_start = ev.pos()

    def _img_mouse_move(self, ev):
        if not self.dragging:
            return
        self.reset_hide_timer()

    def _img_mouse_release(self, ev):
        self.dragging = False
        self.reset_hide_timer()

    # ---------- Color pickers ----------
    def choose_text_color(self):
        c = QColorDialog.getColor()
        if c.isValid():
            self.default_text_color = (c.red(), c.green(), c.blue(), c.alpha())

    def choose_fill_color(self):
        c = QColorDialog.getColor()
        if c.isValid():
            self.default_fill = (c.red(), c.green(), c.blue(), c.alpha())

    def choose_stroke_color(self):
        c = QColorDialog.getColor()
        if c.isValid():
            self.default_stroke = (c.red(), c.green(), c.blue(), c.alpha())

    # ---------- Effects ----------
    def rotate90(self):
        self.working = self.working.rotate(-90, expand=True)
        self.update_display()

    def negative(self):
        r, g, b, a = self.working.split()
        rgb = Image.merge("RGB", (r, g, b))
        neg = ImageOps.invert(rgb)
        self.working = Image.merge("RGBA", (*neg.split(), a))
        self.update_display()

    def blackwhite(self):
        bw = ImageOps.grayscale(self.working.convert("RGB")).convert("RGBA")
        self.working = bw
        self.update_display()

    # ---------- Save ----------
    def save_overwrite(self):
        final = self.working.copy()
        draw = ImageDraw.Draw(final)
        for L in self.layers:
            if L["type"] == "text":
                f = ImageFont.truetype("DejaVuSans.ttf", L["font_size"])
                bbox = draw.textbbox((L["x"], L["y"]), L["text"], font=f)
                tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
                draw.text((L["x"] - tw // 2, L["y"] - th // 2), L["text"], font=f, fill=L["color"])
            elif L["type"] == "shape":
                x1, y1, x2, y2 = L["bbox"]
                s = L["shape"]
                if s == "rectangle":
                    draw.rectangle([x1, y1, x2, y2], outline=L["stroke_color"], width=L["stroke"])
                elif s == "ellipse":
                    draw.ellipse([x1, y1, x2, y2], outline=L["stroke_color"], width=L["stroke"])
                elif s == "line":
                    draw.line([x1, y1, x2, y2], fill=L["stroke_color"], width=L["stroke"])
        final.convert("RGB").save(self.image_path)
        self.layers = []
        QMessageBox.information(self, "Saved", f"Saved: {self.image_path}")
        if self.on_saved_callback:
            self.on_saved_callback()

    def save_as_new(self):
        final = self.working.copy()
        draw = ImageDraw.Draw(final)
        for L in self.layers:
            if L["type"] == "text":
                f = ImageFont.truetype("DejaVuSans.ttf", L["font_size"])
                bbox = draw.textbbox((L["x"], L["y"]), L["text"], font=f)
                tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
                draw.text((L["x"] - tw // 2, L["y"] - th // 2), L["text"], font=f, fill=L["color"])
        fname = f"photo_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.jpg"
        path = os.path.join(PHOTO_FOLDER, fname)
        final.convert("RGB").save(path)
        QMessageBox.information(self, "Saved", f"Saved new file: {path}")
        if self.on_saved_callback:
            self.on_saved_callback()


# ---------------- Main Gallery ----------------
class PhotoGalleryPlugin(QWidget):
    def __init__(self, parent=None, apps=None, cfg=None):
        super().__init__(parent)
        self.setFixedSize(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.move(0, 0)
        self.setWindowTitle("Photo Gallery")
        ensure_folder()
        self.init_ui()
        self.load_thumbnails()

    def init_ui(self):
        v = QVBoxLayout(self)
        self.setLayout(v)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        content = QWidget()
        self.grid = QGridLayout(content)
        self.scroll.setWidget(content)
        v.addWidget(self.scroll)

        self.scroll.viewport().setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents, True)
        self.scroll.grabGesture(Qt.GestureType.PanGesture)
        self.scroll.event = self._touch_scroll_event

        b = QHBoxLayout()
        for txt, fn in [("Refresh", self.load_thumbnails),
                        ("Import...", self.import_image),
                        ("Open Folder", self.open_folder)]:
            btn = QPushButton(txt)
            btn.clicked.connect(fn)
            b.addWidget(btn)
        v.addLayout(b)

    def _touch_scroll_event(self, event):
        if event.type() == event.Type.Gesture:
            g = event.gesture(Qt.GestureType.PanGesture)
            if g:
                bar = self.scroll.verticalScrollBar()
                bar.setValue(bar.value() - g.delta().y())
                return True
        return super().event(event)

    def load_thumbnails(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        files = sorted(f for f in os.listdir(PHOTO_FOLDER) if os.path.splitext(f)[1].lower() in SUPPORTED_EXTS)
        col = row = 0
        for f in files:
            path = os.path.join(PHOTO_FOLDER, f)
            try:
                img = Image.open(path).convert("RGBA")
            except Exception:
                continue
            img.thumbnail(THUMBNAIL_SIZE)
            qpix = pil_to_qpixmap(img)
            lbl = ClickableLabel()
            lbl.setPixmap(qpix)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setFixedSize(THUMBNAIL_SIZE[0] + 8, THUMBNAIL_SIZE[1] + 8)
            lbl.clicked.connect(partial(self.open_editor, path))
            cap = QLabel(f)
            cap.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cap.setStyleSheet("color:white;")
            container = QWidget()
            v = QVBoxLayout(container)
            v.addWidget(lbl)
            v.addWidget(cap)
            self.grid.addWidget(container, row, col)
            col += 1
            if col >= 4:
                col = 0
                row += 1

    def open_editor(self, path):
        dlg = ImageEditorDialog(path, self, self.load_thumbnails)
        dlg.exec()
        self.load_thumbnails()

    def import_image(self):
        fpath, _ = QFileDialog.getOpenFileName(self, "Import Image", "", "Images (*.png *.jpg *.jpeg *.bmp *.gif)")
        if not fpath:
            return
        fname = f"photo_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}{os.path.splitext(fpath)[1]}"
        dst = os.path.join(PHOTO_FOLDER, fname)
        with open(fpath, "rb") as fr, open(dst, "wb") as fw:
            fw.write(fr.read())
        QMessageBox.information(self, "Imported", f"Imported: {dst}")
        self.load_thumbnails()

    def open_folder(self):
        try:
            os.system(f"xdg-open '{PHOTO_FOLDER}' &")
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))


# ------------- Launcher Entry Point -------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = PhotoGalleryPlugin()
    w.show()
    sys.exit(app.exec())
