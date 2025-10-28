#!/usr/bin/env python3

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
from PyQt6.QtCore import Qt, QSize, pyqtSignal

# --- Folder setup ---
plugin_folder = os.path.dirname(os.path.abspath(__file__))
PHOTO_FOLDER = os.path.join(plugin_folder, "/home/kali/Pictures/SavedPictures")

THUMBNAIL_SIZE = (180, 120)
WINDOW_WIDTH = 1015
WINDOW_HEIGHT = 550
SUPPORTED_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".gif")


# --- Helper conversions between PIL and QPixmap ---
def pil_to_qpixmap(img: Image.Image) -> QPixmap:
    if img.mode not in ("RGBA", "RGB"):
        img = img.convert("RGBA")
    qt_img = ImageQt.ImageQt(img)
    return QPixmap.fromImage(QImage(qt_img))


# --- Clickable thumbnail ---
class ClickableLabel(QLabel):
    clicked = pyqtSignal()
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()


# --- Fullscreen editor dialog ---
class ImageEditorDialog(QDialog):
    def __init__(self, image_path, parent=None, on_saved_callback=None):
        super().__init__(parent)
        self.image_path = image_path
        self.on_saved_callback = on_saved_callback
        self.original = Image.open(self.image_path).convert("RGBA")
        self.working = self.original.copy()
        self.current_shape = None
        self.shape_start = None
        self.shape_end = None
        self.drawing = False

        self.text_color = (255, 255, 255, 255)
        self.fill_color = (0, 0, 0, 0)
        self.stroke_color = (255, 0, 0, 255)

        self.init_ui()
        self.update_display()
        self.setWindowFlag(Qt.WindowType.Window)
        self.setModal(True)

    def init_ui(self):
        v = QVBoxLayout()
        self.setLayout(v)
        self.setWindowState(self.windowState() | Qt.WindowState.WindowFullScreen)

        # --- Image display ---
        self.image_label = QLabel(self)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("background-color: black;")
        v.addWidget(self.image_label, 1)

        # --- Bottom toolbar ---
        toolbar = QFrame()
        toolbar.setFrameShape(QFrame.Shape.StyledPanel)
        toolbar.setStyleSheet("background-color: rgba(30,30,30,220);")
        toolbar.setFixedHeight(110)
        toolbar_layout = QHBoxLayout(toolbar)
        v.addWidget(toolbar)

        # --- Transform buttons ---
        for text, fn in [
            ("Rotate 90°", self.rotate90),
            ("Negative", self.negative),
            ("Black & White", self.blackwhite),
        ]:
            b = QPushButton(text)
            b.clicked.connect(fn)
            toolbar_layout.addWidget(b)

        # --- Text tools ---
        toolbar_layout.addSpacing(10)
        toolbar_layout.addWidget(QLabel("Text:"))
        self.text_input = QLineEdit()
        self.text_input.setPlaceholderText("Enter text")
        toolbar_layout.addWidget(self.text_input)
        self.font_size = QSpinBox()
        self.font_size.setRange(8, 200)
        self.font_size.setValue(24)
        toolbar_layout.addWidget(self.font_size)
        b_color = QPushButton("Text Color")
        b_color.clicked.connect(self.choose_text_color)
        toolbar_layout.addWidget(b_color)
        b_add = QPushButton("Add Text")
        b_add.clicked.connect(self.add_text_to_image)
        toolbar_layout.addWidget(b_add)

        # --- Shape tools ---
        toolbar_layout.addSpacing(10)
        toolbar_layout.addWidget(QLabel("Shape:"))
        self.shape_combo = QComboBox()
        self.shape_combo.addItems(["None", "Rectangle", "Ellipse", "Line"])
        toolbar_layout.addWidget(self.shape_combo)
        toolbar_layout.addWidget(QLabel("Stroke"))
        self.stroke_spin = QSpinBox()
        self.stroke_spin.setRange(1, 50)
        self.stroke_spin.setValue(3)
        toolbar_layout.addWidget(self.stroke_spin)
        b_fill = QPushButton("Fill Color")
        b_fill.clicked.connect(self.choose_fill_color)
        toolbar_layout.addWidget(b_fill)
        b_stroke = QPushButton("Stroke Color")
        b_stroke.clicked.connect(self.choose_stroke_color)
        toolbar_layout.addWidget(b_stroke)
        b_place = QPushButton("Place Shape")
        b_place.clicked.connect(self.start_place_shape)
        toolbar_layout.addWidget(b_place)

        # --- Save / Back buttons (always visible) ---
        toolbar_layout.addSpacing(20)
        save_btn = QPushButton("💾 Save (overwrite)")
        save_btn.clicked.connect(self.save_overwrite)
        toolbar_layout.addWidget(save_btn)

        save_new_btn = QPushButton("🆕 Save as New")
        save_new_btn.clicked.connect(self.save_as_new)
        toolbar_layout.addWidget(save_new_btn)

        back_btn = QPushButton("⬅ Back to Gallery")
        back_btn.clicked.connect(self.close)
        toolbar_layout.addWidget(back_btn)

        # --- Mouse drawing ---
        self.image_label.mousePressEvent = self._mouse_press
        self.image_label.mouseMoveEvent = self._mouse_move
        self.image_label.mouseReleaseEvent = self._mouse_release

    def update_display(self):
        qpix = pil_to_qpixmap(self.working)
        screen_rect = QApplication.primaryScreen().availableGeometry()
        qpix = qpix.scaled(screen_rect.width(), screen_rect.height() - 120,
                           Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
        self.image_label.setPixmap(qpix)

    # --- Image transforms ---
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

    # --- Text and color helpers ---
    def choose_text_color(self):
        c = QColorDialog.getColor()
        if c.isValid():
            self.text_color = (c.red(), c.green(), c.blue(), c.alpha())

    def choose_fill_color(self):
        c = QColorDialog.getColor()
        if c.isValid():
            self.fill_color = (c.red(), c.green(), c.blue(), c.alpha())

    def choose_stroke_color(self):
        c = QColorDialog.getColor()
        if c.isValid():
            self.stroke_color = (c.red(), c.green(), c.blue(), c.alpha())

    def add_text_to_image(self):
        text = self.text_input.text().strip()
        if not text:
            QMessageBox.information(self, "No text", "Please enter some text first.")
            return
        font_size = max(8, int(self.font_size.value()))
        draw = ImageDraw.Draw(self.working)
        try:
            font = ImageFont.truetype("DejaVuSans.ttf", font_size)
        except Exception:
            font = ImageFont.load_default()
        w, h = self.working.size
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        pos = ((w - tw) // 2, (h - th) // 2)
        draw.text(pos, text, fill=self.text_color, font=font)
        self.update_display()

    # --- Shape drawing ---
    def start_place_shape(self):
        sel = self.shape_combo.currentText()
        if sel == "None":
            QMessageBox.information(self, "Shape", "Select a shape first.")
            return
        self.current_shape = sel.lower()
        QMessageBox.information(self, "Place shape", "Click and drag on the image to place the shape.")

    def _mouse_press(self, ev):
        if self.current_shape and ev.button() == Qt.MouseButton.LeftButton:
            self.drawing = True
            self.shape_start = ev.pos()

    def _mouse_move(self, ev):
        if not (self.drawing and self.current_shape):
            return
        self.shape_end = ev.pos()
        overlay = self.working.copy()
        self._draw_shape(overlay)
        self.image_label.setPixmap(pil_to_qpixmap(overlay).scaled(
            self.image_label.pixmap().size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation))

    def _mouse_release(self, ev):
        if self.drawing and self.current_shape:
            self.drawing = False
            self._draw_shape(self.working)
            self.current_shape = None
            self.update_display()

    def _draw_shape(self, target_img):
        if not (self.shape_start and self.shape_end):
            return
        draw = ImageDraw.Draw(target_img)
        stroke = int(self.stroke_spin.value())
        fill = tuple(self.fill_color)
        stroke_col = tuple(self.stroke_color)
        x1, y1 = self.shape_start.x(), self.shape_start.y()
        x2, y2 = self.shape_end.x(), self.shape_end.y()
        x1, x2 = sorted((x1, x2))
        y1, y2 = sorted((y1, y2))
        if self.current_shape == "rectangle":
            if fill[3] != 0: draw.rectangle([x1, y1, x2, y2], fill=fill)
            draw.rectangle([x1, y1, x2, y2], outline=stroke_col, width=stroke)
        elif self.current_shape == "ellipse":
            if fill[3] != 0: draw.ellipse([x1, y1, x2, y2], fill=fill)
            draw.ellipse([x1, y1, x2, y2], outline=stroke_col, width=stroke)
        elif self.current_shape == "line":
            draw.line([x1, y1, x2, y2], fill=stroke_col, width=stroke)

    # --- Saving ---
    def save_overwrite(self):
        try:
            self.working.convert("RGB").save(self.image_path)
            if self.on_saved_callback:
                self.on_saved_callback()
        except Exception as e:
            QMessageBox.warning(self, "Save failed", str(e))

    def save_as_new(self):
        try:
            ext = os.path.splitext(self.image_path)[1].lower()
            fname = f"photo_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}{ext}"
            fpath = os.path.join(PHOTO_FOLDER, fname)
            os.makedirs(PHOTO_FOLDER, exist_ok=True)
            self.working.convert("RGB").save(fpath)
            if self.on_saved_callback:
                self.on_saved_callback()
        except Exception as e:
            QMessageBox.warning(self, "Save failed", str(e))

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key.Key_Escape:
            self.close()


# --- Main plugin widget ---
class PhotoGalleryPlugin(QWidget):
    def __init__(self, parent=None, apps=None, cfg=None):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle("Photo Gallery")
        self.setFixedSize(WINDOW_WIDTH, WINDOW_HEIGHT)
        os.makedirs(PHOTO_FOLDER, exist_ok=True)
        self.init_ui()
        self.load_thumbnails()

    def init_ui(self):
        main_layout = QVBoxLayout()
        self.setLayout(main_layout)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        self.grid = QGridLayout(scroll_content)
        self.scroll.setWidget(scroll_content)
        main_layout.addWidget(self.scroll)

        self.scroll.viewport().setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents, True)
        self.scroll.grabGesture(Qt.GestureType.PanGesture)
        self.scroll.event = self._touch_scroll_event

        btn_layout = QHBoxLayout()
        for text, fn in [
            ("Refresh", self.load_thumbnails),
            ("Import...", self.import_image),
            ("Open Folder", self.open_folder),
        ]:
            b = QPushButton(text)
            b.clicked.connect(fn)
            btn_layout.addWidget(b)
        main_layout.addLayout(btn_layout)

    def _touch_scroll_event(self, event):
        if event.type() == event.Type.Gesture:
            gesture = event.gesture(Qt.GestureType.PanGesture)
            if gesture:
                bar = self.scroll.verticalScrollBar()
                bar.setValue(bar.value() - gesture.delta().y())
                return True
        return super().event(event)

    def load_thumbnails(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        files = sorted([f for f in os.listdir(PHOTO_FOLDER)
                        if os.path.splitext(f)[1].lower() in SUPPORTED_EXTS])
        r, c = 0, 0
        for fname in files:
            path = os.path.join(PHOTO_FOLDER, fname)
            try:
                img = Image.open(path).convert("RGBA")
            except Exception:
                continue
            thumb = img.copy()
            thumb.thumbnail(THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
            qpix = pil_to_qpixmap(thumb)

            lbl = ClickableLabel()
            lbl.setFixedSize(QSize(THUMBNAIL_SIZE[0] + 8, THUMBNAIL_SIZE[1] + 8))
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setPixmap(qpix)
            lbl.clicked.connect(partial(self.open_editor, path))

            caption = QLabel(fname)
            caption.setStyleSheet("color:white; font-size:10pt;")
            caption.setAlignment(Qt.AlignmentFlag.AlignCenter)

            container = QWidget()
            vbox = QVBoxLayout(container)
            vbox.addWidget(lbl)
            vbox.addWidget(caption)
            self.grid.addWidget(container, r, c)

            c += 1
            if c >= 4:
                c, r = 0, r + 1

    def open_editor(self, image_path):
        dlg = ImageEditorDialog(image_path, parent=self, on_saved_callback=self.load_thumbnails)
        dlg.exec()

    def import_image(self):
        fpath, _ = QFileDialog.getOpenFileName(self, "Import Image", "", "Images (*.png *.jpg *.jpeg *.bmp *.gif)")
        if not fpath:
            return
        try:
            ext = os.path.splitext(fpath)[1].lower()
            fname = f"photo_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}{ext}"
            dst = os.path.join(PHOTO_FOLDER, fname)
            with open(fpath, "rb") as fr, open(dst, "wb") as fw:
                fw.write(fr.read())
            self.load_thumbnails()
        except Exception as e:
            QMessageBox.warning(self, "Import failed", str(e))

    def open_folder(self):
        try:
            if sys.platform.startswith("linux"):
                os.system(f'xdg-open "{PHOTO_FOLDER}" &')
            elif sys.platform.startswith("win"):
                os.startfile(PHOTO_FOLDER)
            elif sys.platform.startswith("darwin"):
                os.system(f'open "{PHOTO_FOLDER}" &')
        except Exception as e:
            QMessageBox.warning(self, "Open folder failed", str(e))


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = PhotoGalleryPlugin()
    w.show()
    sys.exit(app.exec())
