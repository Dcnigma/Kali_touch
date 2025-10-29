#!/usr/bin/env python3
"""
photoGallery_plugin.py
Final polished touch-friendly photo gallery + editor plugin.

Features:
- Fixed window size WINDOW_WIDTH x WINDOW_HEIGHT (kiosk-friendly)
- Thumbnails grid with swipe scrolling
- Editor with:
  * Floating Back button (top-left, always visible)
  * Bottom icons-only toolbar (auto-hide after inactivity)
  * Movable/selectable/editable layers (text + shapes)
  * Double-tap a layer to edit (text content/size/color or shape properties)
  * Delete selected layer (✖)
  * Save (overwrite) and Save As New
- Uses Pillow + PyQt6. Uses DejaVuSans.ttf if available.
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
    QSpinBox, QColorDialog, QLineEdit, QFrame, QSizePolicy, QFormLayout
)
from PyQt6.QtGui import QPixmap, QImage, QColor
from PyQt6.QtCore import Qt, QSize, pyqtSignal, QTimer, QPoint

# ---------------- Configuration ----------------
plugin_folder = os.path.dirname(os.path.abspath(__file__))
# Keep the user's exact requested form:
PHOTO_FOLDER = os.path.join(plugin_folder, "/home/kali/Pictures/SavedPictures")

THUMBNAIL_SIZE = (180, 120)
WINDOW_WIDTH = 1015
WINDOW_HEIGHT = 550
SUPPORTED_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".gif")
TOOLBAR_HIDE_MS = 4000  # milliseconds


# ---------------- Helpers ----------------
def pil_to_qpixmap(img: Image.Image) -> QPixmap:
    if img.mode not in ("RGBA", "RGB"):
        img = img.convert("RGBA")
    qt_img = ImageQt.ImageQt(img)
    return QPixmap.fromImage(QImage(qt_img))


def ensure_folder():
    os.makedirs(PHOTO_FOLDER, exist_ok=True)


def load_default_font(size):
    """Try DejaVuSans.ttf, fallback to default PIL font."""
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except Exception:
        return ImageFont.load_default()


# ---------------- Clickable Label (with position-aware double click) ----------------
class ClickableLabel(QLabel):
    clicked = pyqtSignal(object)       # emits QPoint
    doubleClicked = pyqtSignal(object) # emits QPoint

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(ev.pos())

    def mouseDoubleClickEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self.doubleClicked.emit(ev.pos())


# ---------------- Edit dialogs ----------------
class TextEditDialog(QDialog):
    def __init__(self, layer, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Text Layer")
        self.layer = layer
        layout = QFormLayout(self)
        self.text_edit = QLineEdit(layer.get("text", ""))
        self.size_spin = QSpinBox()
        self.size_spin.setRange(8, 300)
        self.size_spin.setValue(layer.get("font_size", 24))
        self.color_btn = QPushButton("🎨")
        self.color_btn.clicked.connect(self.pick_color)
        layout.addRow("Text:", self.text_edit)
        layout.addRow("Font size:", self.size_spin)
        layout.addRow(self.color_btn)
        btn_row = QHBoxLayout()
        ok = QPushButton("OK")
        ok.clicked.connect(self.accept)
        canc = QPushButton("Cancel")
        canc.clicked.connect(self.reject)
        btn_row.addWidget(ok)
        btn_row.addWidget(canc)
        layout.addRow(btn_row)

    def pick_color(self):
        c = QColorDialog.getColor()
        if c.isValid():
            self.layer["color"] = (c.red(), c.green(), c.blue(), c.alpha())

    def accept(self):
        self.layer["text"] = self.text_edit.text()
        self.layer["font_size"] = self.size_spin.value()
        super().accept()


class ShapeEditDialog(QDialog):
    def __init__(self, layer, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Shape Layer")
        self.layer = layer
        layout = QFormLayout(self)
        self.shape_combo = QComboBox()
        self.shape_combo.addItems(["rectangle", "ellipse", "line"])
        self.shape_combo.setCurrentText(layer.get("shape", "rectangle"))
        self.stroke_spin = QSpinBox()
        self.stroke_spin.setRange(1, 200)
        self.stroke_spin.setValue(layer.get("stroke", 3))
        self.fill_btn = QPushButton("🩸")
        self.fill_btn.clicked.connect(self.pick_fill)
        self.stroke_btn = QPushButton("✏️")
        self.stroke_btn.clicked.connect(self.pick_stroke)
        layout.addRow("Shape:", self.shape_combo)
        layout.addRow("Stroke width:", self.stroke_spin)
        layout.addRow(self.fill_btn)
        layout.addRow(self.stroke_btn)
        btn_row = QHBoxLayout()
        ok = QPushButton("OK")
        ok.clicked.connect(self.accept)
        canc = QPushButton("Cancel")
        canc.clicked.connect(self.reject)
        btn_row.addWidget(ok)
        btn_row.addWidget(canc)
        layout.addRow(btn_row)

    def pick_fill(self):
        c = QColorDialog.getColor()
        if c.isValid():
            self.layer["fill_color"] = (c.red(), c.green(), c.blue(), c.alpha())

    def pick_stroke(self):
        c = QColorDialog.getColor()
        if c.isValid():
            self.layer["stroke_color"] = (c.red(), c.green(), c.blue(), c.alpha())

    def accept(self):
        self.layer["shape"] = self.shape_combo.currentText()
        self.layer["stroke"] = self.stroke_spin.value()
        super().accept()


# ---------------- Image Editor Dialog ----------------
class ImageEditorDialog(QDialog):
    def __init__(self, image_path, parent=None, on_saved_callback=None):
        super().__init__(parent)
        self.image_path = image_path
        self.on_saved_callback = on_saved_callback

        # Fixed plugin window size & top-left position
        self.setFixedSize(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.move(0, 0)

        # Base and working images
        self.base_image = Image.open(self.image_path).convert("RGBA")
        self.working = self.base_image.copy()

        # Layers list
        # Layer structure:
        # text: {'id', 'type':'text', 'text', 'font_size', 'color', 'x', 'y'}
        # shape: {'id', 'type':'shape', 'shape', 'bbox':(x1,y1,x2,y2), 'stroke', 'stroke_color', 'fill_color'}
        self.layers = []
        self.selected_layer_id = None
        self.dragging = False
        self.drag_offset = (0, 0)

        # defaults
        self.default_text_color = (255, 255, 255, 255)
        self.default_fill = (0, 0, 0, 0)
        self.default_stroke = (255, 0, 0, 255)

        # init UI
        self.init_ui()
        self.update_display()

        # toolbar hide timer
        self.hide_timer = QTimer(self)
        self.hide_timer.setInterval(TOOLBAR_HIDE_MS)
        self.hide_timer.timeout.connect(self.hide_toolbar)
        self.reset_hide_timer()

    def init_ui(self):
        self.setWindowTitle(os.path.basename(self.image_path))
        layout = QVBoxLayout(self)
        self.setLayout(layout)

        # image display label (clickable)
        self.image_label = ClickableLabel(self)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("background-color: black;")
        self.image_label.setFixedSize(WINDOW_WIDTH, WINDOW_HEIGHT - 120)
        layout.addWidget(self.image_label, 1)

        # connect label signals
        self.image_label.clicked.connect(self.on_image_click)
        self.image_label.doubleClicked.connect(self.on_image_double_click)

        # Back button (floating, always visible)
        self.back_btn = QPushButton("⬅️", self)
        self.back_btn.setToolTip("Back to gallery")
        self.back_btn.setStyleSheet("background: rgba(40,40,40,200); color: white; padding:6px; border-radius:6px;")
        self.back_btn.setFixedSize(48, 36)
        self.back_btn.move(12, 12)
        self.back_btn.clicked.connect(self.close)
        self.back_btn.show()

        # Delete selected layer button (hidden until selection)
        self.delete_btn = QPushButton("✖", self)
        self.delete_btn.setToolTip("Delete selected layer")
        self.delete_btn.setStyleSheet("background: rgba(200,50,50,220); color: white; border-radius:10px;")
        self.delete_btn.setFixedSize(34, 34)
        self.delete_btn.clicked.connect(self.delete_selected_layer)
        self.delete_btn.hide()

        # toolbar (icons-only)
        self.toolbar = QFrame(self)
        self.toolbar.setStyleSheet("background-color: rgba(30,30,30,220);")
        tb = QHBoxLayout(self.toolbar)
        self.toolbar.setFixedHeight(110)
        layout.addWidget(self.toolbar)

        # --- toolbar icons (emoji) ---
        def make_btn(icon, tooltip):
            b = QPushButton(icon)
            b.setToolTip(tooltip)
            b.setFixedSize(48, 48)
            return b

        b_rot = make_btn("🔄", "Rotate 90°")
        b_rot.clicked.connect(self.rotate90)
        tb.addWidget(b_rot)

        b_neg = make_btn("🌑", "Negative")
        b_neg.clicked.connect(self.negative)
        tb.addWidget(b_neg)

        b_bw = make_btn("⚫⚪", "Black & White")
        b_bw.clicked.connect(self.blackwhite)
        tb.addWidget(b_bw)

        # text controls
        tb.addWidget(QLabel(" "))  # small spacer
        self.text_input = QLineEdit()
        self.text_input.setPlaceholderText("Enter text")
        self.text_input.setFixedWidth(200)
        tb.addWidget(self.text_input)
        self.font_spin = QSpinBox()
        self.font_spin.setRange(8, 300)
        self.font_spin.setValue(24)
        self.font_spin.setFixedWidth(70)
        tb.addWidget(self.font_spin)

        b_text_color = make_btn("🎨", "Text color")
        b_text_color.clicked.connect(self.choose_text_color)
        tb.addWidget(b_text_color)

        b_add_text = make_btn("🅰️", "Add text")
        b_add_text.clicked.connect(self.add_text_layer)
        tb.addWidget(b_add_text)

        # shape controls
        tb.addWidget(QLabel(" "))
        self.shape_combo = QComboBox()
        self.shape_combo.addItems(["None", "Rectangle", "Ellipse", "Line"])
        tb.addWidget(self.shape_combo)
        self.stroke_spin = QSpinBox()
        self.stroke_spin.setRange(1, 200)
        self.stroke_spin.setValue(3)
        self.stroke_spin.setFixedWidth(70)
        tb.addWidget(self.stroke_spin)

        b_fill = make_btn("🩸", "Fill color")
        b_fill.clicked.connect(self.choose_fill_color)
        tb.addWidget(b_fill)

        b_stroke = make_btn("✏️", "Stroke color")
        b_stroke.clicked.connect(self.choose_stroke_color)
        tb.addWidget(b_stroke)

        b_add_shape = make_btn("⬛", "Add shape")
        b_add_shape.clicked.connect(self.add_shape_layer)
        tb.addWidget(b_add_shape)

        # save icons
        tb.addWidget(QLabel(" "))
        b_save = make_btn("💾", "Save (overwrite)")
        b_save.clicked.connect(self.save_overwrite)
        tb.addWidget(b_save)

        b_save_new = make_btn("🆕", "Save as new")
        b_save_new.clicked.connect(self.save_as_new)
        tb.addWidget(b_save_new)

        # info label (small)
        self.info_label = QLabel("")
        self.info_label.setStyleSheet("color: white;")
        tb.addWidget(self.info_label)

        # mouse handlers for dragging are implemented by label events
        self.image_label.mousePressEvent = self._img_mouse_press
        self.image_label.mouseMoveEvent = self._img_mouse_move
        self.image_label.mouseReleaseEvent = self._img_mouse_release

        # reset hide timer when toolbar pressed
        for w in [b_rot, b_neg, b_bw, b_text_color, b_add_text, b_fill, b_stroke, b_add_shape, b_save, b_save_new]:
            try:
                w.pressed.connect(self.reset_hide_timer)
            except Exception:
                pass

    # ---------------- Utility helpers ----------------
    def _get_layer(self, lid):
        for L in self.layers:
            if L["id"] == lid:
                return L
        return None

    def _get_layer_at(self, img_x, img_y):
        # hit test top-most layer under the point (img coords)
        for L in reversed(self.layers):
            if L["type"] == "text":
                draw_tmp = ImageDraw.Draw(self.working)
                try:
                    fnt = load_default_font(L.get("font_size", 24))
                except Exception:
                    fnt = ImageFont.load_default()
                bbox = draw_tmp.textbbox((L["x"], L["y"]), L.get("text", ""), font=fnt)
                x1, y1, x2, y2 = bbox
            else:
                x1, y1, x2, y2 = L["bbox"]
                if L.get("shape") == "line":
                    pad = max(8, L.get("stroke", 3))
                    x1 -= pad; y1 -= pad; x2 += pad; y2 += pad
            if x1 <= img_x <= x2 and y1 <= img_y <= y2:
                return L
        return None

    def _display_info(self):
        pix = self.image_label.pixmap()
        if pix is None:
            return None
        disp_w = pix.width(); disp_h = pix.height()
        lbl_w = self.image_label.width(); lbl_h = self.image_label.height()
        off_x = max(0, (lbl_w - disp_w) // 2); off_y = max(0, (lbl_h - disp_h) // 2)
        return {'pix_w': disp_w, 'pix_h': disp_h, 'lbl_w': lbl_w, 'lbl_h': lbl_h, 'off_x': off_x, 'off_y': off_y}

    def to_image_coords(self, qpos):
        info = self._display_info()
        if not info:
            return None
        x = qpos.x() - info['off_x']; y = qpos.y() - info['off_y']
        if x < 0: x = 0
        if y < 0: y = 0
        img_w, img_h = self.working.size
        fx = img_w / info['pix_w'] if info['pix_w'] else 1.0
        fy = img_h / info['pix_h'] if info['pix_h'] else 1.0
        img_x = int(x * fx); img_y = int(y * fy)
        img_x = max(0, min(img_w - 1, img_x)); img_y = max(0, min(img_h - 1, img_y))
        return (img_x, img_y)

    def from_image_to_display(self, x, y):
        info = self._display_info()
        if not info:
            return None
        img_w, img_h = self.working.size
        fx = info['pix_w'] / img_w if img_w else 1.0
        fy = info['pix_h'] / img_h if img_h else 1.0
        dx = int(x * fx) + info['off_x']; dy = int(y * fy) + info['off_y']
        return QPoint(dx, dy)

    # ---------------- Layer management ----------------
    def add_text_layer(self):
        text = self.text_input.text().strip()
        if not text:
            QMessageBox.information(self, "No text", "Enter text first.")
            return
        w, h = self.working.size
        L = {
            'id': uuid.uuid4().hex,
            'type': 'text',
            'text': text,
            'font_size': int(self.font_spin.value()),
            'color': self.default_text_color,
            'x': w // 2,
            'y': h // 2
        }
        self.layers.append(L)
        self.select_layer(L['id'])
        self.update_display()
        self.reset_hide_timer()

    def add_shape_layer(self):
        sel = self.shape_combo.currentText().lower()
        if sel == 'none':
            QMessageBox.information(self, "Shape", "Select a shape first.")
            return
        w, h = self.working.size
        m = min(w, h) // 6
        bbox = (w // 2 - m, h // 2 - m, w // 2 + m, h // 2 + m)
        L = {
            'id': uuid.uuid4().hex,
            'type': 'shape',
            'shape': sel,
            'bbox': bbox,
            'stroke': int(self.stroke_spin.value()),
            'stroke_color': self.default_stroke,
            'fill_color': self.default_fill
        }
        self.layers.append(L)
        self.select_layer(L['id'])
        self.update_display()
        self.reset_hide_timer()

    def select_layer(self, lid):
        self.selected_layer_id = lid
        L = self._get_layer(lid)
        if L and L.get('type'):
            self.info_label.setText(f"Selected: {lid[:8]}")
            self.delete_btn.show()
        else:
            self.info_label.setText("")
            self.delete_btn.hide()
        self.update_display()

    def deselect_layer(self):
        self.selected_layer_id = None
        self.info_label.setText("")
        self.delete_btn.hide()
        self.update_display()

    def delete_selected_layer(self):
        if not self.selected_layer_id:
            return
        self.layers = [L for L in self.layers if L['id'] != self.selected_layer_id]
        self.selected_layer_id = None
        self.delete_btn.hide()
        self.update_display()

    # ---------------- Mouse interactions ----------------
    def on_image_click(self, qpos):
        # click without drag: mapped by label's clicked signal with pos
        # we rely on mouse press/release for selection; keep this for reset timer
        self.reset_hide_timer()

    def on_image_double_click(self, qpos):
        # double-click event gives a QPoint in label coords
        self.reset_hide_timer()
        img_pos = self.to_image_coords(qpos)
        if not img_pos:
            return
        hit = self._get_layer_at(img_pos[0], img_pos[1])
        if not hit:
            return
        self.select_layer(hit['id'])
        # open appropriate edit dialog
        if hit['type'] == 'text':
            dlg = TextEditDialog(hit, self)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                # updated in dialog
                pass
        else:
            dlg = ShapeEditDialog(hit, self)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                # updated in dialog
                pass
        self.update_display()

    def _img_mouse_press(self, ev):
        self.reset_hide_timer()
        if ev.button() != Qt.MouseButton.LeftButton:
            return
        qpos = ev.pos()
        img_pos = self.to_image_coords(qpos)
        if not img_pos:
            return
        img_x, img_y = img_pos
        hit = self._get_layer_at(img_x, img_y)
        if hit:
            self.select_layer(hit['id'])
            # compute offset for dragging
            if hit['type'] == 'text':
                self.drag_offset = (img_x - hit['x'], img_y - hit['y'])
            else:
                x1, y1, x2, y2 = hit['bbox']
                self.drag_offset = (img_x - x1, img_y - y1)
            self.dragging = True
        else:
            self.deselect_layer()
            self.dragging = False

    def _img_mouse_move(self, ev):
        if not self.dragging or not self.selected_layer_id:
            return
        self.reset_hide_timer()
        qpos = ev.pos()
        img_pos = self.to_image_coords(qpos)
        if not img_pos:
            return
        img_x, img_y = img_pos
        L = self._get_layer(self.selected_layer_id)
        if not L:
            return
        if L['type'] == 'text':
            dx, dy = self.drag_offset
            L['x'] = int(img_x - dx)
            L['y'] = int(img_y - dy)
        else:
            dx, dy = self.drag_offset
            w = L['bbox'][2] - L['bbox'][0]; h = L['bbox'][3] - L['bbox'][1]
            new_x1 = int(img_x - dx); new_y1 = int(img_y - dy)
            L['bbox'] = (new_x1, new_y1, new_x1 + w, new_y1 + h)
        self.update_display()

    def _img_mouse_release(self, ev):
        self.dragging = False
        self.reset_hide_timer()

    # ---------------- Rendering ----------------
    def update_display(self):
        canvas = self.working.copy()
        draw = ImageDraw.Draw(canvas)

        for L in self.layers:
            if L['type'] == 'text':
                try:
                    fnt = load_default_font(L.get('font_size', 24))
                except Exception:
                    fnt = ImageFont.load_default()
                txt = L.get('text', '')
                bbox = draw.textbbox((L['x'], L['y']), txt, font=fnt)
                tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
                draw.text((L['x'] - tw // 2, L['y'] - th // 2), txt, font=fnt, fill=tuple(L.get('color', self.default_text_color)))
                if self.selected_layer_id == L['id']:
                    # highlight selection rect
                    rect = (L['x'] - tw // 2 - 4, L['y'] - th // 2 - 4, L['x'] + tw // 2 + 4, L['y'] + th // 2 + 4)
                    draw.rectangle(rect, outline=(255, 255, 0, 200), width=2)
            else:
                x1, y1, x2, y2 = L['bbox']
                stroke = L.get('stroke', 3)
                stroke_col = L.get('stroke_color', self.default_stroke)
                fill = L.get('fill_color', self.default_fill)
                s = L.get('shape', 'rectangle')
                if s == 'rectangle':
                    if fill and fill[3] != 0:
                        draw.rectangle([x1, y1, x2, y2], fill=tuple(fill))
                    draw.rectangle([x1, y1, x2, y2], outline=tuple(stroke_col), width=stroke)
                elif s == 'ellipse':
                    if fill and fill[3] != 0:
                        draw.ellipse([x1, y1, x2, y2], fill=tuple(fill))
                    draw.ellipse([x1, y1, x2, y2], outline=tuple(stroke_col), width=stroke)
                else:  # line
                    draw.line([x1, y1, x2, y2], fill=tuple(stroke_col), width=stroke)
                if self.selected_layer_id == L['id']:
                    draw.rectangle([x1 - 4, y1 - 4, x2 + 4, y2 + 4], outline=(255, 255, 0, 200), width=2)

        # convert and scale to label
        pix = pil_to_qpixmap(canvas)
        scaled = pix.scaled(self.image_label.width(), self.image_label.height(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.image_label.setPixmap(scaled)

        # position delete button near selected layer (display coords)
        if self.selected_layer_id:
            L = self._get_layer(self.selected_layer_id)
            if L:
                if L['type'] == 'text':
                    draw_tmp = ImageDraw.Draw(self.working)
                    try:
                        fnt = load_default_font(L.get('font_size', 24))
                    except Exception:
                        fnt = ImageFont.load_default()
                    bbox = draw_tmp.textbbox((L['x'], L['y']), L.get('text', ''), font=fnt)
                    tx2 = L['x'] + (bbox[2] - bbox[0]) // 2
                    ty1 = L['y'] - (bbox[3] - bbox[1]) // 2
                    disp_pt = self.from_image_to_display(tx2, ty1)
                else:
                    x1, y1, x2, y2 = L['bbox']
                    disp_pt = self.from_image_to_display(x2, y1)
                if disp_pt:
                    dx = disp_pt.x() + 6
                    dy = disp_pt.y() - 6
                    dx = max(4, min(self.width() - 36, dx))
                    dy = max(4, min(self.height() - 36, dy))
                    self.delete_btn.move(dx, dy)
                    self.delete_btn.show()
                else:
                    self.delete_btn.hide()
        else:
            self.delete_btn.hide()

    # ---------------- Apply & Save ----------------
    def apply_all_layers_to_image(self, base_img):
        final = base_img.copy()
        draw = ImageDraw.Draw(final)
        for L in self.layers:
            if L['type'] == 'text':
                try:
                    fnt = load_default_font(L.get('font_size', 24))
                except Exception:
                    fnt = ImageFont.load_default()
                bbox = draw.textbbox((L['x'], L['y']), L.get('text', ''), font=fnt)
                tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
                top_left = (L['x'] - tw // 2, L['y'] - th // 2)
                draw.text(top_left, L.get('text', ''), font=fnt, fill=tuple(L.get('color', self.default_text_color)))
            else:
                x1, y1, x2, y2 = L['bbox']
                stroke = L.get('stroke', 3)
                stroke_col = L.get('stroke_color', self.default_stroke)
                fill = L.get('fill_color', self.default_fill)
                s = L.get('shape', 'rectangle')
                if s == 'rectangle':
                    if fill and fill[3] != 0:
                        draw.rectangle([x1, y1, x2, y2], fill=tuple(fill))
                    draw.rectangle([x1, y1, x2, y2], outline=tuple(stroke_col), width=stroke)
                elif s == 'ellipse':
                    if fill and fill[3] != 0:
                        draw.ellipse([x1, y1, x2, y2], fill=tuple(fill))
                    draw.ellipse([x1, y1, x2, y2], outline=tuple(stroke_col), width=stroke)
                else:
                    draw.line([x1, y1, x2, y2], fill=tuple(stroke_col), width=stroke)
        return final

    def save_overwrite(self):
        try:
            final = self.apply_all_layers_to_image(self.working)
            final.convert("RGB").save(self.image_path)
            self.base_image = final.copy()
            self.working = final.copy()
            self.layers = []
            self.selected_layer_id = None
            if self.on_saved_callback:
                self.on_saved_callback()
            QMessageBox.information(self, "Saved", f"Saved: {self.image_path}")
            self.update_display()
        except Exception as e:
            QMessageBox.warning(self, "Save failed", str(e))

    def save_as_new(self):
        try:
            final = self.apply_all_layers_to_image(self.working)
            ext = os.path.splitext(self.image_path)[1].lower() or ".jpg"
            fname = f"photo_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}{ext}"
            fpath = os.path.join(PHOTO_FOLDER, fname)
            ensure_folder()
            final.convert("RGB").save(fpath)
            if self.on_saved_callback:
                self.on_saved_callback()
            QMessageBox.information(self, "Saved As New", f"Saved new file: {fpath}")
        except Exception as e:
            QMessageBox.warning(self, "Save failed", str(e))

    # ---------------- Effects ----------------
    def rotate90(self):
        self.working = self.working.rotate(-90, expand=True)
        w, h = self.working.size
        # rotate approximate layer coords (simple transform)
        for L in self.layers:
            if L['type'] == 'text':
                x, y = L['x'], L['y']
                L['x'], L['y'] = y, (w - x)
            else:
                x1, y1, x2, y2 = L['bbox']
                L['bbox'] = (y1, w - x2, y2, w - x1)
        self.update_display()
        self.reset_hide_timer()

    def negative(self):
        r, g, b, a = self.working.split()
        neg = ImageOps.invert(Image.merge("RGB", (r, g, b)))
        self.working = Image.merge("RGBA", (*neg.split(), a))
        self.update_display()
        self.reset_hide_timer()

    def blackwhite(self):
        bw = ImageOps.grayscale(self.working.convert("RGB")).convert("RGBA")
        self.working = bw
        self.update_display()
        self.reset_hide_timer()

    # ---------------- Color pickers ----------------
    def choose_text_color(self):
        c = QColorDialog.getColor()
        if c.isValid():
            if self.selected_layer_id:
                L = self._get_layer(self.selected_layer_id)
                if L and L.get('type') == 'text':
                    L['color'] = (c.red(), c.green(), c.blue(), c.alpha())
                else:
                    self.default_text_color = (c.red(), c.green(), c.blue(), c.alpha())
            else:
                self.default_text_color = (c.red(), c.green(), c.blue(), c.alpha())
            self.update_display()
            self.reset_hide_timer()

    def choose_fill_color(self):
        c = QColorDialog.getColor()
        if c.isValid():
            if self.selected_layer_id:
                L = self._get_layer(self.selected_layer_id)
                if L and L.get('type') == 'shape':
                    L['fill_color'] = (c.red(), c.green(), c.blue(), c.alpha())
                else:
                    self.default_fill = (c.red(), c.green(), c.blue(), c.alpha())
            else:
                self.default_fill = (c.red(), c.green(), c.blue(), c.alpha())
            self.update_display()
            self.reset_hide_timer()

    def choose_stroke_color(self):
        c = QColorDialog.getColor()
        if c.isValid():
            if self.selected_layer_id:
                L = self._get_layer(self.selected_layer_id)
                if L and L.get('type') == 'shape':
                    L['stroke_color'] = (c.red(), c.green(), c.blue(), c.alpha())
                else:
                    self.default_stroke = (c.red(), c.green(), c.blue(), c.alpha())
            else:
                self.default_stroke = (c.red(), c.green(), c.blue(), c.alpha())
            self.update_display()
            self.reset_hide_timer()

    # ---------------- Toolbar auto-hide ----------------
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


# ---------------- Gallery Plugin ----------------
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
        layout = QVBoxLayout(self)
        self.setLayout(layout)

        # Scroll area for thumbnails
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        content = QWidget()
        self.grid = QGridLayout(content)
        self.scroll.setWidget(content)
        layout.addWidget(self.scroll)

        # enable touch gestures
        self.scroll.viewport().setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents, True)
        self.scroll.grabGesture(Qt.GestureType.PanGesture)
        self.scroll.event = self._touch_scroll_event

        # bottom controls
        btnrow = QHBoxLayout()
        b_refresh = QPushButton("Refresh")
        b_refresh.clicked.connect(self.load_thumbnails)
        btnrow.addWidget(b_refresh)
        b_import = QPushButton("Import...")
        b_import.clicked.connect(self.import_image)
        btnrow.addWidget(b_import)
        b_open = QPushButton("Open Folder")
        b_open.clicked.connect(self.open_folder)
        btnrow.addWidget(b_open)
        layout.addLayout(btnrow)

    def _touch_scroll_event(self, event):
        if event.type() == event.Type.Gesture:
            g = event.gesture(Qt.GestureType.PanGesture)
            if g:
                bar = self.scroll.verticalScrollBar()
                bar.setValue(bar.value() - g.delta().y())
                return True
        return super().event(event)

    def load_thumbnails(self):
        # clear grid
        while self.grid.count():
            it = self.grid.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        try:
            files = sorted([f for f in os.listdir(PHOTO_FOLDER) if os.path.splitext(f)[1].lower() in SUPPORTED_EXTS])
        except Exception:
            files = []
        col = 0; row = 0; cols = 4
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
            cap = QLabel(fname)
            cap.setStyleSheet("color:white;")
            cap.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cont = QWidget()
            v = QVBoxLayout(cont)
            v.addWidget(lbl)
            v.addWidget(cap)
            self.grid.addWidget(cont, row, col)
            col += 1
            if col >= cols:
                col = 0; row += 1

    def open_editor(self, path):
        dlg = ImageEditorDialog(path, self, self.load_thumbnails)
        dlg.exec()
        # refresh thumbnails on return
        self.load_thumbnails()

    def import_image(self):
        fpath, _ = QFileDialog.getOpenFileName(self, "Import Image", "", "Images (*.png *.jpg *.jpeg *.bmp *.gif)")
        if not fpath:
            return
        ext = os.path.splitext(fpath)[1] or ".jpg"
        fname = f"photo_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}{ext}"
        dst = os.path.join(PHOTO_FOLDER, fname)
        ensure_folder()
        with open(fpath, "rb") as fr, open(dst, "wb") as fw:
            fw.write(fr.read())
        QMessageBox.information(self, "Imported", f"Imported: {dst}")
        self.load_thumbnails()

    def open_folder(self):
        try:
            if sys.platform.startswith("linux"):
                os.system(f"xdg-open '{PHOTO_FOLDER}' &")
            elif sys.platform.startswith("win"):
                os.startfile(PHOTO_FOLDER)
            elif sys.platform.startswith("darwin"):
                os.system(f"open '{PHOTO_FOLDER}' &")
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))


# ---------------- Standalone test ----------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = PhotoGalleryPlugin()
    w.show()
    sys.exit(app.exec())
