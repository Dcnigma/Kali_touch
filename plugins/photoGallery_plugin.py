#!/usr/bin/env python3
"""
photoGallery_plugin.py
Polished plugin:
- Fixed 1015x550 layout
- Floating semi-transparent toolbar (icons-only, 90px high)
- Add Text & Add Shape open dialogs (no inline toolbar controls)
- Resizable shapes by dragging selection corners (free resize)
- Selectable/draggable/editable layers (text & shapes)
- Transparent color option, DejaVuSans fallback
- Touch-friendly gallery
"""

import os
import sys
import uuid
import socket
import json

from datetime import datetime
from functools import partial

from PIL import Image, ImageOps, ImageQt, ImageDraw, ImageFont

from PyQt6.QtWidgets import (
    QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QGridLayout,
    QApplication, QScrollArea, QFileDialog, QMessageBox, QDialog, QComboBox,
    QSpinBox, QColorDialog, QLineEdit, QFrame, QSizePolicy, QFormLayout,
    QGraphicsDropShadowEffect
)
from PyQt6.QtGui import QPixmap, QImage, QColor
from PyQt6.QtCore import Qt, QSize, pyqtSignal, QTimer, QPoint

# ---------------- Config ----------------
plugin_folder = os.path.dirname(os.path.abspath(__file__))
PHOTO_FOLDER = os.path.join(plugin_folder, "/home/kali/Pictures/SavedPictures")

THUMBNAIL_SIZE = (290, 210)
WINDOW_WIDTH = 1015
WINDOW_HEIGHT = 550
SUPPORTED_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".gif")
TOOLBAR_HIDE_MS = 6000  # 6s
TOOLBAR_HEIGHT = 60     # reduced by ~20px as requested
HANDLE_SIZE_PX = 14     # corner handle sensitive area in display->image coords threshold

# ---------------- Helpers ----------------
def pil_to_qpixmap(img: Image.Image) -> QPixmap:
    if img.mode not in ("RGBA", "RGB"):
        img = img.convert("RGBA")
    qt_img = ImageQt.ImageQt(img)
    return QPixmap.fromImage(QImage(qt_img))


def ensure_folder():
    os.makedirs(PHOTO_FOLDER, exist_ok=True)


def load_default_font(size):
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except Exception:
        return ImageFont.load_default()


# ---------------- ClickableLabel ----------------
class ClickableLabel(QLabel):
    clicked = pyqtSignal(object)       # emits QPoint
    doubleClicked = pyqtSignal(object) # emits QPoint

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(ev.pos())

    def mouseDoubleClickEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self.doubleClicked.emit(ev.pos())


# ---------------- Dialogs ----------------
class TextEditDialog(QDialog):
    def __init__(self, layer=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Text")
        self.layer = layer or {}
        layout = QFormLayout(self)
        self.text_edit = QLineEdit(self.layer.get("text", ""))
        self.size_spin = QSpinBox()
        self.size_spin.setRange(8, 400)
        self.size_spin.setValue(self.layer.get("font_size", 24))
        self.color_btn = QPushButton("🎨")
        self.color_btn.clicked.connect(self.pick_color)
        layout.addRow("Text:", self.text_edit)
        layout.addRow("Font size:", self.size_spin)
        layout.addRow(self.color_btn)
        btn_row = QHBoxLayout()
        ok = QPushButton("OK"); ok.clicked.connect(self.accept)
        canc = QPushButton("Cancel"); canc.clicked.connect(self.reject)
        btn_row.addWidget(ok); btn_row.addWidget(canc)
        layout.addRow(btn_row)

    def pick_color(self):
        c = QColorDialog.getColor()
        if c.isValid():
            self.layer["color"] = (c.red(), c.green(), c.blue(), c.alpha())
        else:
            r = QMessageBox.question(self, "Transparent?", "Set text color to Transparent?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if r == QMessageBox.StandardButton.Yes:
                self.layer["color"] = (0,0,0,0)

    def accept(self):
        self.layer["text"] = self.text_edit.text()
        self.layer["font_size"] = self.size_spin.value()
        super().accept()


class ShapeEditDialog(QDialog):
    def __init__(self, layer=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Shape")
        self.layer = layer or {}
        layout = QFormLayout(self)
        self.shape_combo = QComboBox()
        self.shape_combo.addItems(["rectangle", "ellipse", "line"])
        self.shape_combo.setCurrentText(self.layer.get("shape", "rectangle"))
        self.stroke_spin = QSpinBox(); self.stroke_spin.setRange(1, 200); self.stroke_spin.setValue(self.layer.get("stroke", 3))
        self.fill_btn = QPushButton("🩸"); self.fill_btn.clicked.connect(self.pick_fill)
        self.stroke_btn = QPushButton("✏️"); self.stroke_btn.clicked.connect(self.pick_stroke)
        layout.addRow("Shape:", self.shape_combo)
        layout.addRow("Stroke width:", self.stroke_spin)
        layout.addRow(self.fill_btn)
        layout.addRow(self.stroke_btn)
        btn_row = QHBoxLayout()
        ok = QPushButton("OK"); ok.clicked.connect(self.accept)
        canc = QPushButton("Cancel"); canc.clicked.connect(self.reject)
        btn_row.addWidget(ok); btn_row.addWidget(canc)
        layout.addRow(btn_row)

    def pick_fill(self):
        c = QColorDialog.getColor()
        if c.isValid():
            self.layer["fill_color"] = (c.red(), c.green(), c.blue(), c.alpha())
        else:
            r = QMessageBox.question(self, "Transparent?", "Set fill to Transparent?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if r == QMessageBox.StandardButton.Yes:
                self.layer["fill_color"] = (0,0,0,0)

    def pick_stroke(self):
        c = QColorDialog.getColor()
        if c.isValid():
            self.layer["stroke_color"] = (c.red(), c.green(), c.blue(), c.alpha())
        else:
            r = QMessageBox.question(self, "Transparent?", "Set stroke to Transparent?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if r == QMessageBox.StandardButton.Yes:
                self.layer["stroke_color"] = (0,0,0,0)

    def accept(self):
        self.layer["shape"] = self.shape_combo.currentText()
        self.layer["stroke"] = self.stroke_spin.value()
        super().accept()


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
        self.resizing = False
        self.resize_corner = None  # 'nw','ne','sw','se'
        self.drag_offset = (0,0)

        self.default_text_color = (255,255,255,255)
        self.default_fill = (0,0,0,0)
        self.default_stroke = (255,0,0,255)

        self.init_ui()
        self.update_display()

        self.hide_timer = QTimer(self)
        self.hide_timer.setInterval(TOOLBAR_HIDE_MS)
        self.hide_timer.timeout.connect(self.hide_toolbar)
        self.reset_hide_timer()

    def init_ui(self):
        self.setWindowTitle(os.path.basename(self.image_path))
        layout = QVBoxLayout(self)
        self.setLayout(layout)

        # image area
        self.image_label = ClickableLabel(self)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("background-color: black;")
        self.image_label.setFixedSize(WINDOW_WIDTH, WINDOW_HEIGHT - TOOLBAR_HEIGHT)
        layout.addWidget(self.image_label, 1)

        # connect signals for click/double-click
        #self.image_label.clicked.connect(self.on_image_click)
        #self.image_label.doubleClicked.connect(self.on_image_double_click)

        # wheel resets hide timer
        def _wheel(ev):
            self.reset_hide_timer()
            QLabel.wheelEvent(self.image_label, ev)
        self.image_label.wheelEvent = _wheel

        # floating back button
        self.back_btn = QPushButton("⬅️", self)
        self.back_btn.setToolTip("Back to gallery")
        self.back_btn.setFixedSize(48,36)
        self.back_btn.move(12,12)
        self.back_btn.setStyleSheet("background: rgba(40,40,40,200); color: white; border-radius:6px;")
        self.back_btn.clicked.connect(self.close)
        self.back_btn.show()

        # delete button
        self.delete_btn = QPushButton("✖", self)
        self.delete_btn.setToolTip("Delete selected layer")
        self.delete_btn.setFixedSize(34,34)
        self.delete_btn.setStyleSheet("background: rgba(200,50,50,220); color: white; border-radius:10px;")
        self.delete_btn.clicked.connect(self.delete_selected_layer)
        self.delete_btn.hide()

        # floating toolbar anchored to bottom
        self.toolbar = QFrame(self)
        self.toolbar.setStyleSheet("background-color: rgba(30,30,30,170); border-top:1px solid rgba(255,255,255,20);")
        self.toolbar.setFixedHeight(TOOLBAR_HEIGHT)
        self.toolbar.setFixedWidth(WINDOW_WIDTH)
        self.toolbar.move(0, WINDOW_HEIGHT - TOOLBAR_HEIGHT)
        tb = QHBoxLayout(self.toolbar)
        tb.setContentsMargins(6,6,6,6)
        tb.setSpacing(8)

        def make_icon_btn(icon, tooltip):
            b = QPushButton(icon)
            b.setToolTip(tooltip)
            b.setFixedSize(44,44)
            b.setStyleSheet("font-size:16px; background: rgba(255,255,255,10); color: white; border-radius:8px;")
            glow = QGraphicsDropShadowEffect(self)
            glow.setBlurRadius(8)
            glow.setOffset(0,0)
            glow.setColor(QColor(0,0,0,180))
            b.setGraphicsEffect(glow)
            return b

        # rotate / negative / bw
        b_rot = make_icon_btn("🔄","Rotate 90°"); b_rot.clicked.connect(self.rotate90); tb.addWidget(b_rot)
        b_neg = make_icon_btn("🌑","Negative"); b_neg.clicked.connect(self.negative); tb.addWidget(b_neg)
        b_bw  = make_icon_btn("⚫⚪","Black & White"); b_bw.clicked.connect(self.blackwhite); tb.addWidget(b_bw)

        tb.addWidget(QLabel(" "))  # spacer

        # add text -> open dialog
        b_add_text = make_icon_btn("🅰️","Add Text"); b_add_text.clicked.connect(self.open_add_text_dialog); tb.addWidget(b_add_text)
        # add shape -> open dialog
        b_add_shape = make_icon_btn("⬛","Add Shape"); b_add_shape.clicked.connect(self.open_add_shape_dialog); tb.addWidget(b_add_shape)

        tb.addWidget(QLabel(" "))  # spacer

        # color pickers act on selected layer or default Don't need this
        b_text_color = make_icon_btn("🎨","Text Color"); b_text_color.clicked.connect(self.choose_text_color); tb.addWidget(b_text_color)
        b_fill = make_icon_btn("🩸","Fill Color"); b_fill.clicked.connect(self.choose_fill_color); tb.addWidget(b_fill)
        b_stroke = make_icon_btn("✏️","Stroke Color"); b_stroke.clicked.connect(self.choose_stroke_color); tb.addWidget(b_stroke)

        tb.addWidget(QLabel(" "))

        b_save = make_icon_btn("💾","Save (overwrite)"); b_save.clicked.connect(self.save_overwrite); tb.addWidget(b_save)
        b_save_new = make_icon_btn("🆕","Save As New"); b_save_new.clicked.connect(self.save_as_new); tb.addWidget(b_save_new)

        self.info_label = QLabel(""); self.info_label.setStyleSheet("color:white;"); tb.addWidget(self.info_label)

        self.toolbar.show()

        # connect low-level mouse handlers for drag/resize selection
        self.image_label.mousePressEvent = self._img_mouse_press
        self.image_label.mouseMoveEvent = self._img_mouse_move
        self.image_label.mouseReleaseEvent = self._img_mouse_release

        # reset hide timer when toolbar buttons pressed
        for w in [b_rot,b_neg,b_bw,b_add_text,b_add_shape,b_text_color,b_fill,b_stroke,b_save,b_save_new]:
            try:
                w.pressed.connect(self.reset_hide_timer)
            except Exception:
                pass

    # ---------------- Basic helpers ----------------
    def _get_layer(self, lid):
        for L in self.layers:
            if L.get("id") == lid:
             return L
        return None

    def _get_layer_at(self, img_x, img_y):
        # top-most hit test, using textbbox for text layers
        for L in reversed(self.layers):
            if L["type"] == "text":
                draw_tmp = ImageDraw.Draw(self.working)
                fnt = load_default_font(L.get("font_size", 24))
                bbox = draw_tmp.textbbox((L["x"], L["y"]), L.get("text", ""), font=fnt)
                x1,y1,x2,y2 = bbox
            else:
                x1,y1,x2,y2 = L["bbox"]
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

    # ---------------- Add via dialogs ----------------
    def open_add_text_dialog(self):
        dlg = TextEditDialog(parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            L = dlg.layer
            # ensure required keys
            w,h = self.working.size
            L.setdefault('id', uuid.uuid4().hex)
            L.setdefault('type','text')
            L.setdefault('text', '')
            L.setdefault('font_size', 24)
            L.setdefault('color', self.default_text_color)
            L.setdefault('x', w//2); L.setdefault('y', h//2)
            self.layers.append(L)
            self.select_layer(L['id'])
            self.update_display()
            self.reset_hide_timer()

    def open_add_shape_dialog(self):
        dlg = ShapeEditDialog(parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            L = dlg.layer
            w,h = self.working.size
            m = min(w,h)//6
            bbox = (w//2 - m, h//2 - m, w//2 + m, h//2 + m)
            layer = {
                'id': uuid.uuid4().hex,
                'type': 'shape',
                'shape': L.get('shape','rectangle'),
                'bbox': bbox,
                'stroke': L.get('stroke',3),
                'stroke_color': L.get('stroke_color', self.default_stroke),
                'fill_color': L.get('fill_color', self.default_fill)
            }
            self.layers.append(layer)
            self.select_layer(layer['id'])
            self.update_display()
            self.reset_hide_timer()

    # ---------------- Color pickers (transparent option) ----------------
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
        else:
            r = QMessageBox.question(self, "Transparent?", "Set text color to Transparent?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if r == QMessageBox.StandardButton.Yes:
                if self.selected_layer_id:
                    L = self._get_layer(self.selected_layer_id)
                    if L and L.get('type') == 'text':
                        L['color'] = (0,0,0,0)
                    else:
                        self.default_text_color = (0,0,0,0)
                else:
                    self.default_text_color = (0,0,0,0)
        self.update_display(); self.reset_hide_timer()

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
        else:
            r = QMessageBox.question(self, "Transparent?", "Set fill to Transparent?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if r == QMessageBox.StandardButton.Yes:
                if self.selected_layer_id:
                    L = self._get_layer(self.selected_layer_id)
                    if L and L.get('type') == 'shape':
                        L['fill_color'] = (0,0,0,0)
                    else:
                        self.default_fill = (0,0,0,0)
                else:
                    self.default_fill = (0,0,0,0)
        self.update_display(); self.reset_hide_timer()

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
        else:
            r = QMessageBox.question(self, "Transparent?", "Set stroke to Transparent?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if r == QMessageBox.StandardButton.Yes:
                if self.selected_layer_id:
                    L = self._get_layer(self.selected_layer_id)
                    if L and L.get('type') == 'shape':
                        L['stroke_color'] = (0,0,0,0)
                    else:
                        self.default_stroke = (0,0,0,0)
                else:
                    self.default_stroke = (0,0,0,0)
        self.update_display(); self.reset_hide_timer()

    # ---------------- Selection / Drag / Resize logic ----------------
    def select_layer(self, lid):
        self.selected_layer_id = lid
        L = self._get_layer(lid)
        if L:
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
        self.layers = [L for L in self.layers if L.get('id') != self.selected_layer_id]
        self.selected_layer_id = None
        self.delete_btn.hide()
        self.update_display()

    def point_near(self, px, py, tx, ty, thresh):
        return abs(px - tx) <= thresh and abs(py - ty) <= thresh

    def find_resize_corner(self, img_x, img_y):
        """Return the corner key if the point is near a corner of selected layer in image coords."""
        L = self._get_layer(self.selected_layer_id) if self.selected_layer_id else None
        if not L or L.get('type') != 'shape':
            return None
        x1,y1,x2,y2 = L['bbox']
        # corners: nw(x1,y1), ne(x2,y1), sw(x1,y2), se(x2,y2)
        # convert handle threshold into image coords by approximating via display scaling:
        info = self._display_info()
        if not info:
            thresh = HANDLE_SIZE_PX
        else:
            # map one handle size display px to image px via fx (use average)
            fx = self.working.size[0] / info['pix_w'] if info['pix_w'] else 1.0
            fy = self.working.size[1] / info['pix_h'] if info['pix_h'] else 1.0
            # choose larger scaling to be safe
            scale = max(fx, fy)
            thresh = int(HANDLE_SIZE_PX * scale) + 1
        if self.point_near(img_x, img_y, x1, y1, thresh):
            return 'nw'
        if self.point_near(img_x, img_y, x2, y1, thresh):
            return 'ne'
        if self.point_near(img_x, img_y, x1, y2, thresh):
            return 'sw'
        if self.point_near(img_x, img_y, x2, y2, thresh):
            return 'se'
        return None

    def _img_mouse_press(self, ev):
        self.reset_hide_timer()
        if ev.button() != Qt.MouseButton.LeftButton:
            return
        qpos = ev.pos()
        img_pos = self.to_image_coords(qpos)
        if not img_pos:
            return
        img_x, img_y = img_pos
        # if selected shape and near a corner -> start resizing
        if self.selected_layer_id:
            corner = self.find_resize_corner(img_x, img_y)
            if corner:
                self.resizing = True
                self.resize_corner = corner
                return
        hit = self._get_layer_at(img_x, img_y)
        if hit:
            self.select_layer(hit['id'])
            if hit['type'] == 'text':
                self.drag_offset = (img_x - hit['x'], img_y - hit['y'])
            else:
                x1,y1,x2,y2 = hit['bbox']
                self.drag_offset = (img_x - x1, img_y - y1)
            self.dragging = True
            self.resizing = False
        else:
            self.deselect_layer()
            self.dragging = False
            self.resizing = False

    def _img_mouse_move(self, ev):
        if not (self.dragging or self.resizing) or not self.selected_layer_id:
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
        if self.resizing and L['type'] == 'shape':
            # free resize by corner
            x1,y1,x2,y2 = L['bbox']
            if self.resize_corner == 'nw':
                x1 = img_x; y1 = img_y
            elif self.resize_corner == 'ne':
                x2 = img_x; y1 = img_y
            elif self.resize_corner == 'sw':
                x1 = img_x; y2 = img_y
            elif self.resize_corner == 'se':
                x2 = img_x; y2 = img_y
            # normalize to ensure x1<x2, y1<y2
            nx1, nx2 = min(x1,x2), max(x1,x2)
            ny1, ny2 = min(y1,y2), max(y1,y2)
            L['bbox'] = (int(nx1), int(ny1), int(nx2), int(ny2))
        elif self.dragging:
            if L['type'] == 'text':
                dx,dy = self.drag_offset
                L['x'] = int(img_x - dx)
                L['y'] = int(img_y - dy)
            else:
                dx,dy = self.drag_offset
                w = L['bbox'][2] - L['bbox'][0]; h = L['bbox'][3] - L['bbox'][1]
                new_x1 = int(img_x - dx); new_y1 = int(img_y - dy)
                L['bbox'] = (new_x1, new_y1, new_x1 + w, new_y1 + h)
        self.update_display()

    def _img_mouse_release(self, ev):
        self.dragging = False
        self.resizing = False
        self.resize_corner = None
        self.reset_hide_timer()

    # ---------------- Rendering ----------------
    def update_display(self):
        canvas = self.working.copy()
        draw = ImageDraw.Draw(canvas)
        for L in self.layers:
            if L['type'] == 'text':
                fnt = load_default_font(L.get('font_size', 24))
                txt = L.get('text','')
                bbox = draw.textbbox((L['x'], L['y']), txt, font=fnt)
                tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
                draw.text((L['x'] - tw//2, L['y'] - th//2), txt, font=fnt, fill=tuple(L.get('color', self.default_text_color)))
                if self.selected_layer_id == L['id']:
                    rect = (L['x'] - tw//2 - 4, L['y'] - th//2 -4, L['x'] + tw//2 + 4, L['y'] + th//2 + 4)
                    draw.rectangle(rect, outline=(255,255,0,200), width=2)
            else:
                x1,y1,x2,y2 = L['bbox']
                stroke = L.get('stroke',3)
                stroke_col = L.get('stroke_color', self.default_stroke)
                fill = L.get('fill_color', self.default_fill)
                s = L.get('shape','rectangle')
                if s == 'rectangle':
                    if fill and fill[3] != 0:
                        draw.rectangle([x1,y1,x2,y2], fill=tuple(fill))
                    draw.rectangle([x1,y1,x2,y2], outline=tuple(stroke_col), width=stroke)
                elif s == 'ellipse':
                    if fill and fill[3] != 0:
                        draw.ellipse([x1,y1,x2,y2], fill=tuple(fill))
                    draw.ellipse([x1,y1,x2,y2], outline=tuple(stroke_col), width=stroke)
                else:
                    draw.line([x1,y1,x2,y2], fill=tuple(stroke_col), width=stroke)
                if self.selected_layer_id == L['id']:
                    draw.rectangle([x1-4,y1-4,x2+4,y2+4], outline=(255,255,0,200), width=2)
                    # draw corner handles for resizing (small squares)
                    corners = [(x1,y1),(x2,y1),(x1,y2),(x2,y2)]
                    for (cx,cy) in corners:
                        draw.rectangle([cx-8,cy-8,cx+8,cy+8], outline=(255,255,0,200), width=2)

        pix = pil_to_qpixmap(canvas)
        scaled = pix.scaled(self.image_label.width(), self.image_label.height(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.image_label.setPixmap(scaled)

        # position delete button near selected layer
        if self.selected_layer_id:
            L = self._get_layer(self.selected_layer_id)
            if L:
                if L['type'] == 'text':
                    draw_tmp = ImageDraw.Draw(self.working)
                    fnt = load_default_font(L.get('font_size',24))
                    bbox = draw_tmp.textbbox((L['x'],L['y']), L.get('text',''), font=fnt)
                    tx2 = L['x'] + (bbox[2]-bbox[0])//2
                    ty1 = L['y'] - (bbox[3]-bbox[1])//2
                    disp_pt = self.from_image_to_display(tx2, ty1)
                else:
                    x1,y1,x2,y2 = L['bbox']
                    disp_pt = self.from_image_to_display(x2, y1)
                if disp_pt:
                    dx = disp_pt.x() + 6; dy = disp_pt.y() - 6
                    dx = max(4, min(self.width()-36, dx)); dy = max(4, min(self.height()-36, dy))
                    self.delete_btn.move(dx, dy)
                    self.delete_btn.show()
                else:
                    self.delete_btn.hide()
        else:
            self.delete_btn.hide()

    # ---------------- Save / Apply ----------------
    def apply_all_layers_to_image(self, base_img):
        final = base_img.copy()
        draw = ImageDraw.Draw(final)
        for L in self.layers:
            if L['type'] == 'text':
                fnt = load_default_font(L.get('font_size',24))
                bbox = draw.textbbox((L['x'],L['y']), L.get('text',''), font=fnt)
                tw,th = bbox[2]-bbox[0], bbox[3]-bbox[1]
                top_left = (L['x'] - tw//2, L['y'] - th//2)
                draw.text(top_left, L.get('text',''), font=fnt, fill=tuple(L.get('color', self.default_text_color)))
            else:
                x1,y1,x2,y2 = L['bbox']
                stroke = L.get('stroke',3)
                stroke_col = L.get('stroke_color', self.default_stroke)
                fill = L.get('fill_color', self.default_fill)
                s = L.get('shape','rectangle')
                if s == 'rectangle':
                    if fill and fill[3] != 0:
                        draw.rectangle([x1,y1,x2,y2], fill=tuple(fill))
                    draw.rectangle([x1,y1,x2,y2], outline=tuple(stroke_col), width=stroke)
                elif s == 'ellipse':
                    if fill and fill[3] != 0:
                        draw.ellipse([x1,y1,x2,y2], fill=tuple(fill))
                    draw.ellipse([x1,y1,x2,y2], outline=tuple(stroke_col), width=stroke)
                else:
                    draw.line([x1,y1,x2,y2], fill=tuple(stroke_col), width=stroke)
        return final

    def save_overwrite(self):
        try:
            final = self.apply_all_layers_to_image(self.working)
            final.convert("RGB").save(self.image_path)
            self.base_image = final.copy(); self.working = final.copy()
        #Sock code for Companion rebecca see rebecca.json for event_map
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
            sock.sendto(json.dumps({"type":"save_data"}).encode(), "/tmp/rebecca.sock")
            sock.close()         
            self.layers = []; self.selected_layer_id = None
            if self.on_saved_callback: self.on_saved_callback()
            QMessageBox.information(self, "Saved", f"Saved: {self.image_path}")
        #Sock code for Companion rebecca see rebecca.json for event_map
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
            sock.sendto(json.dumps({"type":"save_data"}).encode(), "/tmp/rebecca.sock")
            sock.close()            
            self.update_display()
        except Exception as e:
            QMessageBox.warning(self, "Save failed", str(e))

    def save_as_new(self):
        try:
            final = self.apply_all_layers_to_image(self.working)
            ext = os.path.splitext(self.image_path)[1].lower() or ".jpg"
        #Sock code for Companion rebecca see rebecca.json for event_map
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
            sock.sendto(json.dumps({"type":"save_data"}).encode(), "/tmp/rebecca.sock")
            sock.close()            
            fname = f"photo_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}{ext}"
            fpath = os.path.join(PHOTO_FOLDER, fname)
            ensure_folder()
            final.convert("RGB").save(fpath)
            if self.on_saved_callback: self.on_saved_callback()
            QMessageBox.information(self, "Saved As New", f"Saved new file: {fpath}")
        #Sock code for Companion rebecca see rebecca.json for event_map
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
            sock.sendto(json.dumps({"type":"save_data"}).encode(), "/tmp/rebecca.sock")
            sock.close()
        except Exception as e:
            QMessageBox.warning(self, "Save failed", str(e))

    # ---------------- Effects ----------------
    def rotate90(self):
        self.working = self.working.rotate(-90, expand=True)
        w,h = self.working.size
        for L in self.layers:
            if L['type'] == 'text':
                x,y = L['x'], L['y']; L['x'], L['y'] = y, (w - x)
            else:
                x1,y1,x2,y2 = L['bbox']; L['bbox'] = (y1, w - x2, y2, w - x1)
        self.update_display(); self.reset_hide_timer()

    def negative(self):
        r,g,b,a = self.working.split()
        neg = ImageOps.invert(Image.merge("RGB",(r,g,b)))
        self.working = Image.merge("RGBA", (*neg.split(), a))
        self.update_display(); self.reset_hide_timer()

    def blackwhite(self):
        bw = ImageOps.grayscale(self.working.convert("RGB")).convert("RGBA")
        self.working = bw
        self.update_display(); self.reset_hide_timer()

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
    #Sock code for Companion rebecca see rebecca.json for event_map
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        sock.sendto(json.dumps({"type":"save_data"}).encode(), "/tmp/rebecca.sock")
        sock.close()
        super().__init__(parent)
        self.setFixedSize(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.move(0,0)
        self.setWindowTitle("Photo Gallery")
        ensure_folder()
        self.init_ui()
        self.load_thumbnails()

    def init_ui(self):
        layout = QVBoxLayout(self)
        self.setLayout(layout)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        content = QWidget()
        self.grid = QGridLayout(content)
        self.scroll.setWidget(content)
        layout.addWidget(self.scroll)

        # touch gestures
        self.scroll.viewport().setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents, True)
        self.scroll.grabGesture(Qt.GestureType.PanGesture)
        self.scroll.event = self._touch_scroll_event

        # bottom buttons small
        btn_row = QHBoxLayout()
        b_refresh = QPushButton("Refresh"); b_refresh.clicked.connect(self.load_thumbnails); btn_row.addWidget(b_refresh)
        b_import = QPushButton("Import..."); b_import.clicked.connect(self.import_image); btn_row.addWidget(b_import)
        b_open = QPushButton("Open Folder"); b_open.clicked.connect(self.open_folder); btn_row.addWidget(b_open)
        layout.addLayout(btn_row)

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
            it = self.grid.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        try:
            files = sorted([f for f in os.listdir(PHOTO_FOLDER) if os.path.splitext(f)[1].lower() in SUPPORTED_EXTS])
        except Exception:
            files = []
        col=0; row=0; cols=3
        for fname in files:
            path = os.path.join(PHOTO_FOLDER, fname)
            try:
                img = Image.open(path).convert("RGBA")
            except Exception:
                continue
            thumb = img.copy(); thumb.thumbnail(THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
            qpix = pil_to_qpixmap(thumb)
            lbl = ClickableLabel(); lbl.setFixedSize(QSize(THUMBNAIL_SIZE[0]+1,THUMBNAIL_SIZE[1]+1))
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter); lbl.setPixmap(qpix)
            lbl.clicked.connect(partial(self.open_editor, path))
            #cap = QLabel(fname); cap.setStyleSheet("color:white;"); cap.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cont = QWidget(); vbox = QVBoxLayout(cont); vbox.addWidget(lbl); #vbox.addWidget(cap)
            self.grid.addWidget(cont, row, col)
            col += 1
            if col >= cols:
                col = 0; row += 1

    def open_editor(self, path):
        dlg = ImageEditorDialog(path, self, self.load_thumbnails)
        dlg.exec()
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


# ---------------- Standalone Test ----------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = PhotoGalleryPlugin()
    w.show()
    sys.exit(app.exec())
