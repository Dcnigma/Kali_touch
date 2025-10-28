#!/usr/bin/env python3
"""
photoGallery_plugin.py
Photo gallery plugin for your launcher.

Features:
- Hardcoded PHOTO_FOLDER inside plugin folder (auto-created)
- Scrollable thumbnail grid
- Click a thumbnail -> opens fullscreen editor (esc to exit)
- Editor: Rotate (90°), Negative, Black & White, Add Text, Add Shape (rect/ellipse/line)
- Text/shape options via a compact popup docked at bottom
- Save (overwrite) and Save As New (timestamp + uuid)
- Auto-refresh gallery after saving
Requires: PyQt6, Pillow (PIL)

Author: generated for Bart Hamblok
"""
import os
import sys
import uuid
import time
from datetime import datetime
from functools import partial
from io import BytesIO

from PyQt6.QtWidgets import (
    QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QGridLayout,
    QApplication, QScrollArea, QFileDialog, QMessageBox, QDialog, QComboBox,
    QSpinBox, QColorDialog, QLineEdit, QFrame
)
from PyQt6.QtGui import QPixmap, QImage, QAction, QPainter, QPen, QBrush, QColor, QFont
from PyQt6.QtCore import Qt, QSize, pyqtSignal, QRect

from PIL import Image, ImageOps, ImageQt, ImageDraw, ImageFont

# Plugin folder and hardcoded photo folder
plugin_folder = os.path.dirname(os.path.abspath(__file__))
PHOTO_FOLDER = os.path.join(plugin_folder, "photos")

THUMBNAIL_SIZE = (180, 120)  # width, height
WINDOW_WIDTH = 1015
WINDOW_HEIGHT = 570

SUPPORTED_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".gif")


# ---------- Helper conversions between PIL and QPixmap ----------
def pil_to_qpixmap(img: Image.Image) -> QPixmap:
    if img.mode not in ("RGBA", "RGB"):
        img = img.convert("RGBA")
    qt_img = ImageQt.ImageQt(img)
    return QPixmap.fromImage(QImage(qt_img))


def qpixmap_to_pil(qpix: QPixmap) -> Image.Image:
    qimg = qpix.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
    width = qimg.width()
    height = qimg.height()
    ptr = qimg.bits()
    ptr.setsize(qimg.byteCount())
    arr = bytes(ptr)
    img = Image.frombytes("RGBA", (width, height), arr)
    return img.convert("RGBA")


# ---------- Clickable thumbnail label ----------
class ClickableLabel(QLabel):
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()


# ---------- Fullscreen editor dialog ----------
class ImageEditorDialog(QDialog):
    def __init__(self, image_path, parent=None, on_saved_callback=None):
        super().__init__(parent)
        self.setWindowTitle(os.path.basename(image_path))
        self.image_path = image_path
        self.on_saved_callback = on_saved_callback
        self.original = Image.open(self.image_path).convert("RGBA")
        self.working = self.original.copy()
        self.temp_draws = []  # store shapes/text to apply on save (optional)
        self.current_shape = None  # ("rect"/"ellipse"/"line")
        self.shape_start = None
        self.shape_end = None
        self.drawing = False

        self.init_ui()
        self.update_display()

        # Key bindings
        self.setWindowFlag(Qt.WindowType.Window)
        self.setModal(True)

    def init_ui(self):
        v = QVBoxLayout()
        self.setLayout(v)
        self.setWindowState(self.windowState() | Qt.WindowState.WindowFullScreen)

        # Image display label
        self.image_label = QLabel(self)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("background-color: black;")
        self.image_label.setMinimumSize(200, 200)
        v.addWidget(self.image_label, 1)

        # Bottom toolbar (compact popup-like)
        toolbar = QFrame()
        toolbar.setFrameShape(QFrame.Shape.StyledPanel)
        toolbar_layout = QHBoxLayout()
        toolbar.setLayout(toolbar_layout)
        toolbar.setFixedHeight(110)
        toolbar.setStyleSheet("background-color: rgba(30,30,30,220);")
        v.addWidget(toolbar)

        # Left group: basic transforms
        rotate_btn = QPushButton("Rotate 90°")
        rotate_btn.clicked.connect(self.rotate90)
        toolbar_layout.addWidget(rotate_btn)

        negative_btn = QPushButton("Negative")
        negative_btn.clicked.connect(self.negative)
        toolbar_layout.addWidget(negative_btn)

        bw_btn = QPushButton("Black & White")
        bw_btn.clicked.connect(self.blackwhite)
        toolbar_layout.addWidget(bw_btn)

        # Middle group: text controls
        toolbar_layout.addSpacing(10)
        toolbar_layout.addWidget(QLabel("Text:"))
        self.text_input = QLineEdit()
        self.text_input.setPlaceholderText("Enter text")
        toolbar_layout.addWidget(self.text_input)
        self.font_size = QSpinBox()
        self.font_size.setRange(8, 200)
        self.font_size.setValue(24)
        toolbar_layout.addWidget(self.font_size)
        text_color_btn = QPushButton("Text Color")
        text_color_btn.clicked.connect(self.choose_text_color)
        toolbar_layout.addWidget(text_color_btn)
        add_text_btn = QPushButton("Add Text")
        add_text_btn.clicked.connect(self.add_text_to_image)
        toolbar_layout.addWidget(add_text_btn)

        # Right group: shape controls
        toolbar_layout.addSpacing(10)
        toolbar_layout.addWidget(QLabel("Shape:"))
        self.shape_combo = QComboBox()
        self.shape_combo.addItems(["None", "Rectangle", "Ellipse", "Line"])
        toolbar_layout.addWidget(self.shape_combo)
        self.stroke_spin = QSpinBox()
        self.stroke_spin.setRange(1, 50)
        self.stroke_spin.setValue(3)
        toolbar_layout.addWidget(QLabel("Stroke"))
        toolbar_layout.addWidget(self.stroke_spin)
        fill_color_btn = QPushButton("Fill Color")
        fill_color_btn.clicked.connect(self.choose_fill_color)
        toolbar_layout.addWidget(fill_color_btn)
        stroke_color_btn = QPushButton("Stroke Color")
        stroke_color_btn.clicked.connect(self.choose_stroke_color)
        toolbar_layout.addWidget(stroke_color_btn)
        place_shape_btn = QPushButton("Place Shape")
        place_shape_btn.clicked.connect(self.start_place_shape)
        toolbar_layout.addWidget(place_shape_btn)

        # Far-right: save controls
        toolbar_layout.addSpacing(10)
        save_btn = QPushButton("Save (overwrite)")
        save_btn.clicked.connect(self.save_overwrite)
        toolbar_layout.addWidget(save_btn)
        save_new_btn = QPushButton("Save As New")
        save_new_btn.clicked.connect(self.save_as_new)
        toolbar_layout.addWidget(save_new_btn)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        toolbar_layout.addWidget(close_btn)

        # Defaults for colors
        self.text_color = (255, 255, 255, 255)
        self.fill_color = (0, 0, 0, 0)  # default transparent
        self.stroke_color = (255, 0, 0, 255)

        # Mouse events on image_label to place shapes
        self.image_label.mousePressEvent = self._mouse_press
        self.image_label.mouseMoveEvent = self._mouse_move
        self.image_label.mouseReleaseEvent = self._mouse_release

    def update_display(self):
        qpix = pil_to_qpixmap(self.working)
        # scale to fit screen while maintaining aspect ratio
        screen_rect = QApplication.primaryScreen().availableGeometry()
        max_w = screen_rect.width()
        max_h = screen_rect.height() - 120  # leave room for toolbar
        qpix = qpix.scaled(max_w, max_h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.image_label.setPixmap(qpix)
        self.image_label.adjustSize()

    # ---------- Transformations ----------
    def rotate90(self):
        self.working = self.working.rotate(-90, expand=True)
        self.update_display()

    def negative(self):
        r, g, b, a = self.working.split()
        rgb = Image.merge("RGB", (r, g, b))
        neg = ImageOps.invert(rgb)
        neg = Image.merge("RGBA", (*neg.split(), a))
        self.working = neg
        self.update_display()

    def blackwhite(self):
        bw = ImageOps.grayscale(self.working.convert("RGB"))
        bw = bw.convert("RGBA")
        self.working = bw
        self.update_display()

    # ---------- Text & shape tools ----------
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
        # Try to use a default truetype font if available
        try:
            font = ImageFont.truetype("DejaVuSans.ttf", font_size)
        except Exception:
            font = ImageFont.load_default()
        # place text in center by default
        w, h = self.working.size
        tw, th = draw.textsize(text, font=font)
        pos = ((w - tw) // 2, (h - th) // 2)
        draw.text(pos, text, fill=self.text_color, font=font)
        self.update_display()

    def start_place_shape(self):
        sel = self.shape_combo.currentText()
        if sel == "None":
            QMessageBox.information(self, "Shape", "Select a shape first.")
            return
        self.current_shape = sel.lower()
        QMessageBox.information(self, "Place shape",
                                "Click and drag on the image to place the shape. Release to finish.")

    def _mouse_press(self, ev):
        if not self.current_shape:
            return
        if ev.button() == Qt.MouseButton.LeftButton:
            self.drawing = True
            self.shape_start = ev.pos()

    def _mouse_move(self, ev):
        if not (self.drawing and self.current_shape):
            return
        self.shape_end = ev.pos()
        # draw temp overlay on a copy and show it
        overlay = self.working.copy()
        draw = ImageDraw.Draw(overlay)
        # Map label coords back to image coords
        img_label = self.image_label
        pix = img_label.pixmap()
        if pix is None:
            return
        pix_w = pix.width()
        pix_h = pix.height()
        lbl_w = img_label.width()
        lbl_h = img_label.height()
        # compute scale & offset in label
        lbl_pixmap = pix
        # Convert positions relative to pixmap displayed
        sx = (self.shape_start.x() - (lbl_w - pix_w) // 2)
        sy = (self.shape_start.y() - (lbl_h - pix_h) // 2)
        ex = (self.shape_end.x() - (lbl_w - pix_w) // 2)
        ey = (self.shape_end.y() - (lbl_h - pix_h) // 2)
        # scale factor between displayed pixmap and underlying working image
        disp_w, disp_h = pix_w, pix_h
        img_w, img_h = overlay.size
        if disp_w == 0 or disp_h == 0:
            return
        fx = img_w / disp_w
        fy = img_h / disp_h
        rstart = (int(max(0, sx * fx)), int(max(0, sy * fy)))
        rend = (int(max(0, ex * fx)), int(max(0, ey * fy)))
        coords = (rstart[0], rstart[1], rend[0], rend[1])
        stroke = int(self.stroke_spin.value())
        fill = tuple(self.fill_color)
        stroke_col = tuple(self.stroke_color)
        # Normalize coords
        x1, y1, x2, y2 = coords
        x1, x2 = min(x1, x2), max(x1, x2)
        y1, y2 = min(y1, y2), max(y1, y2)
        if self.current_shape == "rectangle":
            if fill and fill[3] != 0:
                draw.rectangle([x1, y1, x2, y2], fill=fill)
            draw.rectangle([x1, y1, x2, y2], outline=stroke_col, width=stroke)
        elif self.current_shape == "ellipse":
            if fill and fill[3] != 0:
                draw.ellipse([x1, y1, x2, y2], fill=fill)
            draw.ellipse([x1, y1, x2, y2], outline=stroke_col, width=stroke)
        elif self.current_shape == "line":
            draw.line([x1, y1, x2, y2], fill=stroke_col, width=stroke)
        # show overlay temporarily
        self.image_label.setPixmap(pil_to_qpixmap(overlay).scaled(self.image_label.pixmap().size(),
                                                                  Qt.AspectRatioMode.KeepAspectRatio,
                                                                  Qt.TransformationMode.SmoothTransformation))

    def _mouse_release(self, ev):
        if not (self.drawing and self.current_shape):
            return
        self.drawing = False
        # finalize shape on working image (re-use logic from _mouse_move)
        if self.shape_start is None or self.shape_end is None:
            return
        # compute transform as in _mouse_move to map to image coords
        pix = self.image_label.pixmap()
        if pix is None:
            return
        pix_w = pix.width()
        pix_h = pix.height()
        lbl_w = self.image_label.width()
        lbl_h = self.image_label.height()
        sx = (self.shape_start.x() - (lbl_w - pix_w) // 2)
        sy = (self.shape_start.y() - (lbl_h - pix_h) // 2)
        ex = (self.shape_end.x() - (lbl_w - pix_w) // 2)
        ey = (self.shape_end.y() - (lbl_h - pix_h) // 2)
        img_w, img_h = self.working.size
        fx = img_w / pix_w if pix_w else 1.0
        fy = img_h / pix_h if pix_h else 1.0
        rstart = (int(max(0, sx * fx)), int(max(0, sy * fy)))
        rend = (int(max(0, ex * fx)), int(max(0, ey * fy)))
        x1, y1 = rstart
        x2, y2 = rend
        x1, x2 = min(x1, x2), max(x1, x2)
        y1, y2 = min(y1, y2), max(y1, y2)
        draw = ImageDraw.Draw(self.working)
        stroke = int(self.stroke_spin.value())
        fill = tuple(self.fill_color)
        stroke_col = tuple(self.stroke_color)
        if self.current_shape == "rectangle":
            if fill and fill[3] != 0:
                draw.rectangle([x1, y1, x2, y2], fill=fill)
            draw.rectangle([x1, y1, x2, y2], outline=stroke_col, width=stroke)
        elif self.current_shape == "ellipse":
            if fill and fill[3] != 0:
                draw.ellipse([x1, y1, x2, y2], fill=fill)
            draw.ellipse([x1, y1, x2, y2], outline=stroke_col, width=stroke)
        elif self.current_shape == "line":
            draw.line([x1, y1, x2, y2], fill=stroke_col, width=stroke)
        self.shape_start = None
        self.shape_end = None
        self.current_shape = None
        self.update_display()

    # ---------- Saving ----------
    def save_overwrite(self):
        try:
            # overwrite original (convert to RGB to avoid alpha issues)
            to_save = self.working.convert("RGB")
            to_save.save(self.image_path)
            QMessageBox.information(self, "Saved", f"Saved: {self.image_path}")
            if self.on_saved_callback:
                self.on_saved_callback()
        except Exception as e:
            QMessageBox.warning(self, "Save failed", str(e))

    def save_as_new(self):
        try:
            base_ext = os.path.splitext(self.image_path)[1].lower()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            unique = uuid.uuid4().hex[:8]
            fname = f"photo_{timestamp}_{unique}{base_ext}"
            fpath = os.path.join(PHOTO_FOLDER, fname)
            os.makedirs(PHOTO_FOLDER, exist_ok=True)
            self.working.convert("RGB").save(fpath)
            QMessageBox.information(self, "Saved As New", f"Saved new file: {fpath}")
            if self.on_saved_callback:
                self.on_saved_callback()
        except Exception as e:
            QMessageBox.warning(self, "Save failed", str(e))

    # Allow Esc to close
    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key.Key_Escape:
            self.close()


# ---------- Main plugin widget ----------
class PhotoGalleryPlugin(QWidget):
    def __init__(self, parent=None, apps=None, cfg=None):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle("Photo Gallery")
        self.setFixedSize(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.move(-50, 0)

        # Background optional: mimic rfids plugin style by loading background.png if present
        bg_path = os.path.join(plugin_folder, "background.png")
        if os.path.exists(bg_path):
            try:
                pix = QPixmap(bg_path).scaled(
                    self.size(), Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation
                )
                palette = self.palette()
                palette.setBrush(self.backgroundRole(), pix)
                self.setAutoFillBackground(True)
                self.setPalette(palette)
            except Exception:
                pass

        # Ensure photo folder exists
        os.makedirs(PHOTO_FOLDER, exist_ok=True)

        self.init_ui()
        self.load_thumbnails()

    def init_ui(self):
        main_layout = QVBoxLayout()
        self.setLayout(main_layout)

        # Header logo area (reuse if logo.png exists)
        self.logo_label = QLabel(self)
        logo_path = os.path.join(plugin_folder, "logo.png")
        if os.path.exists(logo_path):
            pixmap = QPixmap(logo_path).scaled(200, 50, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.logo_label.setPixmap(pixmap)
            self.logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.logo_label, alignment=Qt.AlignmentFlag.AlignCenter)

        # Scroll area for thumbnails
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        self.grid = QGridLayout()
        scroll_content.setLayout(self.grid)
        self.scroll.setWidget(scroll_content)
        main_layout.addWidget(self.scroll)

        # Bottom controls
        btn_layout = QHBoxLayout()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.load_thumbnails)
        btn_layout.addWidget(refresh_btn)
        import_btn = QPushButton("Import...")
        import_btn.clicked.connect(self.import_image)
        btn_layout.addWidget(import_btn)
        open_folder_btn = QPushButton("Open Folder")
        open_folder_btn.clicked.connect(self.open_folder)
        btn_layout.addWidget(open_folder_btn)
        main_layout.addLayout(btn_layout)

    def load_thumbnails(self):
        # clear grid
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # load images
        files = sorted([f for f in os.listdir(PHOTO_FOLDER) if os.path.splitext(f)[1].lower() in SUPPORTED_EXTS])
        col_count = 4
        r = 0
        c = 0
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
            lbl.setStyleSheet("background: #222; border-radius:6px; padding:4px;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setToolTip(fname)
            lbl.setPixmap(qpix.scaled(THUMBNAIL_SIZE[0], THUMBNAIL_SIZE[1], Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            lbl.clicked.connect(partial(self.open_editor, path))
            # caption
            vbox = QVBoxLayout()
            container = QWidget()
            vbox.addWidget(lbl)
            caption = QLabel(fname)
            caption.setStyleSheet("color: white;")
            caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
            caption.setFixedHeight(18)
            vbox.addWidget(caption)
            container.setLayout(vbox)
            self.grid.addWidget(container, r, c)
            c += 1
            if c >= col_count:
                c = 0
                r += 1

    def open_editor(self, image_path):
        dlg = ImageEditorDialog(image_path, parent=self, on_saved_callback=self.load_thumbnails)
        dlg.exec()

    def import_image(self):
        options = QFileDialog.Option.ReadOnly
        fpath, _ = QFileDialog.getOpenFileName(self, "Import Image", "", "Images (*.png *.jpg *.jpeg *.bmp *.gif)", options=options)
        if fpath:
            try:
                base_ext = os.path.splitext(fpath)[1].lower()
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                unique = uuid.uuid4().hex[:8]
                fname = f"photo_{timestamp}_{unique}{base_ext}"
                dst = os.path.join(PHOTO_FOLDER, fname)
                with open(fpath, "rb") as fr, open(dst, "wb") as fw:
                    fw.write(fr.read())
                QMessageBox.information(self, "Imported", f"Imported to {dst}")
                self.load_thumbnails()
            except Exception as e:
                QMessageBox.warning(self, "Import failed", str(e))

    def open_folder(self):
        # attempt to open folder in file manager (best effort)
        try:
            if sys.platform.startswith("linux"):
                os.system(f'xdg-open "{PHOTO_FOLDER}" &')
            elif sys.platform.startswith("win"):
                os.startfile(PHOTO_FOLDER)
            elif sys.platform.startswith("darwin"):
                os.system(f'open "{PHOTO_FOLDER}" &')
        except Exception as e:
            QMessageBox.warning(self, "Open folder failed", str(e))


# For quick testing outside the launcher
if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = PhotoGalleryPlugin()
    w.show()
    sys.exit(app.exec())
