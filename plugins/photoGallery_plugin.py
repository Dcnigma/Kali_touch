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
    QSpinBox, QColorDialog, QLineEdit, QFrame, QSizePolicy
)
from PyQt6.QtGui import QPixmap, QImage, QColor
from PyQt6.QtCore import Qt, QSize, pyqtSignal, QTimer, QPoint

# ---------------- Configuration ----------------
plugin_folder = os.path.dirname(os.path.abspath(__file__))
# User requested exact form:
PHOTO_FOLDER = os.path.join(plugin_folder, "/home/kali/Pictures/SavedPictures")

THUMBNAIL_SIZE = (180, 120)
WINDOW_WIDTH = 1015
WINDOW_HEIGHT = 550
SUPPORTED_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".gif")
TOOLBAR_HIDE_MS = 4000  # hide after 4s of inactivity

# ---------------- Helpers ----------------
def pil_to_qpixmap(img: Image.Image) -> QPixmap:
    if img.mode not in ("RGBA", "RGB"):
        img = img.convert("RGBA")
    qt_img = ImageQt.ImageQt(img)
    return QPixmap.fromImage(QImage(qt_img))


def ensure_folder():
    try:
        os.makedirs(PHOTO_FOLDER, exist_ok=True)
    except Exception:
        pass


# ---------------- Clickable label ----------------
class ClickableLabel(QLabel):
    clicked = pyqtSignal()
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()


# ---------------- Layer structures ----------------
# Layer is a dict with type: 'text'|'shape'
# text layer keys: id, type, text, font_size, color(r,g,b,a), x,y (image coords), anchor
# shape layer keys: id, type, shape ('rectangle'|'ellipse'|'line'), bbox (x1,y1,x2,y2), stroke, stroke_color, fill_color

# ---------------- Image Editor Dialog ----------------
class ImageEditorDialog(QDialog):
    def __init__(self, image_path, parent=None, on_saved_callback=None):
        super().__init__(parent)
        self.image_path = image_path
        self.on_saved_callback = on_saved_callback
        self.base_image = Image.open(self.image_path).convert("RGBA")
        self.working = self.base_image.copy()  # base merged + committed changes
        self.layers = []  # overlay layers (not yet baked)
        self.selected_layer_id = None
        self.dragging = False
        self.drag_offset = (0, 0)

        # defaults
        self.default_text_color = (255, 255, 255, 255)
        self.default_fill = (0, 0, 0, 0)
        self.default_stroke = (255, 0, 0, 255)

        self.init_ui()
        self.update_display()
        # toolbar auto-hide timer
        self.hide_timer = QTimer(self)
        self.hide_timer.setInterval(TOOLBAR_HIDE_MS)
        self.hide_timer.timeout.connect(self.hide_toolbar)
        self.reset_hide_timer()

        # make sure dialog behaves modal-ish but doesn't force fullscreen state
        self.setWindowFlag(Qt.WindowType.Window)
        self.setModal(True)

    def init_ui(self):
        self.setWindowTitle(os.path.basename(self.image_path))
        self.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
        layout = QVBoxLayout(self)
        self.setLayout(layout)

        # Image display area
        self.image_label = QLabel(self)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("background-color: black;")
        self.image_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.image_label, 1)

        # Floating Back button (top-left), always on top
        self.back_btn = QPushButton("← Back to Gallery", self)
        self.back_btn.setStyleSheet("background: rgba(40,40,40,200); color: white; padding:6px; border-radius:6px;")
        self.back_btn.clicked.connect(self.close)
        self.back_btn.setFixedHeight(36)
        self.back_btn.move(12, 12)
        self.back_btn.show()

        # Bottom toolbar (floating-like)
        self.toolbar = QFrame(self)
        self.toolbar.setStyleSheet("background-color: rgba(30,30,30,220);")
        self.toolbar_layout = QHBoxLayout(self.toolbar)
        self.toolbar.setFixedHeight(110)
        layout.addWidget(self.toolbar)

        # --- Left: transforms ---
        btn_rotate = QPushButton("Rotate 90°")
        btn_rotate.clicked.connect(self.rotate90)
        self.toolbar_layout.addWidget(btn_rotate)

        btn_neg = QPushButton("Negative")
        btn_neg.clicked.connect(self.negative)
        self.toolbar_layout.addWidget(btn_neg)

        btn_bw = QPushButton("Black & White")
        btn_bw.clicked.connect(self.blackwhite)
        self.toolbar_layout.addWidget(btn_bw)

        # --- Text tools ---
        self.toolbar_layout.addSpacing(8)
        self.toolbar_layout.addWidget(QLabel("Text:"))
        self.text_input = QLineEdit()
        self.text_input.setPlaceholderText("Enter text")
        self.toolbar_layout.addWidget(self.text_input)
        self.font_spin = QSpinBox()
        self.font_spin.setRange(8, 200)
        self.font_spin.setValue(24)
        self.toolbar_layout.addWidget(self.font_spin)
        btn_text_color = QPushButton("Text Color")
        btn_text_color.clicked.connect(self.choose_text_color)
        self.toolbar_layout.addWidget(btn_text_color)
        btn_add_text = QPushButton("Add Text")
        btn_add_text.clicked.connect(self.add_text_layer)
        self.toolbar_layout.addWidget(btn_add_text)
        btn_apply_text = QPushButton("Apply Text (bake)")
        btn_apply_text.clicked.connect(self.apply_selected_text)
        self.toolbar_layout.addWidget(btn_apply_text)

        # --- Shape tools ---
        self.toolbar_layout.addSpacing(8)
        self.toolbar_layout.addWidget(QLabel("Shape:"))
        self.shape_combo = QComboBox()
        self.shape_combo.addItems(["None", "Rectangle", "Ellipse", "Line"])
        self.toolbar_layout.addWidget(self.shape_combo)
        self.toolbar_layout.addWidget(QLabel("Stroke"))
        self.stroke_spin = QSpinBox()
        self.stroke_spin.setRange(1, 50)
        self.stroke_spin.setValue(3)
        self.toolbar_layout.addWidget(self.stroke_spin)
        btn_fill_color = QPushButton("Fill Color")
        btn_fill_color.clicked.connect(self.choose_fill_color)
        self.toolbar_layout.addWidget(btn_fill_color)
        btn_stroke_color = QPushButton("Stroke Color")
        btn_stroke_color.clicked.connect(self.choose_stroke_color)
        self.toolbar_layout.addWidget(btn_stroke_color)
        btn_add_shape = QPushButton("Add Shape")
        btn_add_shape.clicked.connect(self.add_shape_layer)
        self.toolbar_layout.addWidget(btn_add_shape)
        btn_apply_shape = QPushButton("Apply Shape (bake)")
        btn_apply_shape.clicked.connect(self.apply_selected_shape)
        self.toolbar_layout.addWidget(btn_apply_shape)

        # --- Save controls (always visible) ---
        self.toolbar_layout.addSpacing(8)
        btn_save = QPushButton("💾 Save (overwrite)")
        btn_save.clicked.connect(self.save_overwrite)
        self.toolbar_layout.addWidget(btn_save)
        btn_save_new = QPushButton("🆕 Save As New")
        btn_save_new.clicked.connect(self.save_as_new)
        self.toolbar_layout.addWidget(btn_save_new)

        # --- Selection hints ---
        self.info_label = QLabel("")
        self.info_label.setStyleSheet("color: white;")
        self.toolbar_layout.addWidget(self.info_label)

        # Connect activity signals to show toolbar
        self.image_label.mousePressEvent = self._img_mouse_press
        self.image_label.mouseReleaseEvent = self._img_mouse_release
        self.image_label.mouseMoveEvent = self._img_mouse_move
        # When any button pressed, reset hide timer
        for w in [btn_rotate, btn_neg, btn_bw, btn_text_color, btn_add_text, btn_apply_text,
                  btn_fill_color, btn_stroke_color, btn_add_shape, btn_apply_shape, btn_save, btn_save_new]:
            w.pressed.connect(self.reset_hide_timer)

    # ---------------- Coordinate mapping utilities ----------------
    def _display_info(self):
        """Return info about displayed pixmap size and offsets for mapping coords."""
        pix = self.image_label.pixmap()
        if pix is None:
            return None
        disp_w = pix.width()
        disp_h = pix.height()
        lbl_w = self.image_label.width()
        lbl_h = self.image_label.height()
        # compute top-left offset where pixmap sits inside label (centered)
        offset_x = max(0, (lbl_w - disp_w) // 2)
        offset_y = max(0, (lbl_h - disp_h) // 2)
        return {'pix_w': disp_w, 'pix_h': disp_h, 'lbl_w': lbl_w, 'lbl_h': lbl_h, 'off_x': offset_x, 'off_y': offset_y}

    def to_image_coords(self, pos):
        """Map a QPoint (label coordinates) to image coordinates (working image)."""
        info = self._display_info()
        if not info:
            return None
        x = pos.x() - info['off_x']
        y = pos.y() - info['off_y']
        if x < 0: x = 0
        if y < 0: y = 0
        # scale to working image size
        img_w, img_h = self.working.size
        fx = img_w / info['pix_w'] if info['pix_w'] else 1.0
        fy = img_h / info['pix_h'] if info['pix_h'] else 1.0
        img_x = int(x * fx)
        img_y = int(y * fy)
        img_x = max(0, min(img_w - 1, img_x))
        img_y = max(0, min(img_h - 1, img_y))
        return (img_x, img_y)

    def from_image_coords_to_display(self, x, y):
        """Map image coords to label coords (QPoint)."""
        info = self._display_info()
        if not info:
            return None
        img_w, img_h = self.working.size
        fx = info['pix_w'] / img_w if img_w else 1.0
        fy = info['pix_h'] / img_h if img_h else 1.0
        dx = int(x * fx) + info['off_x']
        dy = int(y * fy) + info['off_y']
        return QPoint(dx, dy)

    # ---------------- Layer management ----------------
    def add_text_layer(self):
        text = self.text_input.text().strip()
        if not text:
            QMessageBox.information(self, "No text", "Please enter text first.")
            return
        font_size = max(8, int(self.font_spin.value()))
        # default position center
        w, h = self.working.size
        layer = {
            'id': uuid.uuid4().hex,
            'type': 'text',
            'text': text,
            'font_size': font_size,
            'color': self.default_text_color,
            'x': w // 2,
            'y': h // 2,
            'anchor': 'center'
        }
        self.layers.append(layer)
        self.select_layer(layer['id'])
        self.update_display()
        self.reset_hide_timer()

    def add_shape_layer(self):
        sel = self.shape_combo.currentText().lower()
        if sel == "none":
            QMessageBox.information(self, "Shape", "Choose a shape type first.")
            return
        # create default bbox (center small box)
        w, h = self.working.size
        margin = min(w, h) // 6
        x1 = (w - margin) // 2
        y1 = (h - margin) // 2
        x2 = (w + margin) // 2
        y2 = (h + margin) // 2
        layer = {
            'id': uuid.uuid4().hex,
            'type': 'shape',
            'shape': sel,  # rectangle/ellipse/line
            'bbox': (x1, y1, x2, y2),
            'stroke': int(self.stroke_spin.value()),
            'stroke_color': self.default_stroke,
            'fill_color': self.default_fill
        }
        self.layers.append(layer)
        self.select_layer(layer['id'])
        self.update_display()
        self.reset_hide_timer()

    def select_layer(self, layer_id):
        self.selected_layer_id = layer_id
        # update info label and controls accordingly
        l = self._get_layer(layer_id)
        if not l:
            self.info_label.setText("")
            return
        if l['type'] == 'text':
            self.info_label.setText(f"Selected text: '{l['text']}'")
            # populate controls
            self.text_input.setText(l['text'])
            self.font_spin.setValue(l['font_size'])
        else:
            self.info_label.setText(f"Selected shape: {l['shape']}")
            self.stroke_spin.setValue(l.get('stroke', 3))
        self.update_display()

    def deselect_layer(self):
        self.selected_layer_id = None
        self.info_label.setText("")
        self.update_display()

    def _get_layer(self, lid):
        for L in self.layers:
            if L['id'] == lid:
                return L
        return None

    # ---------------- Mouse interactions on image for selecting/moving layers ----------------
    def _img_mouse_press(self, ev):
        self.reset_hide_timer()
        pos = ev.pos()
        img_pos = self.to_image_coords(pos)
        if img_pos is None:
            return
        x, y = img_pos
        # find top-most layer hit (iterate reversed)
        hit = None
        for L in reversed(self.layers):
            if L['type'] == 'text':
                # approximate bbox using font metrics
                draw = ImageDraw.Draw(self.working)
                try:
                    fnt = ImageFont.truetype("DejaVuSans.ttf", L['font_size'])
                except Exception:
                    fnt = ImageFont.load_default()
                bbox = draw.textbbox((L['x'], L['y']), L['text'], font=fnt)
                x1, y1, x2, y2 = bbox
            else:
                x1, y1, x2, y2 = L['bbox']
                # for line, create small tappable thickness bounding box
                if L['shape'] == 'line':
                    pad = max(8, L.get('stroke', 3))
                    x1 -= pad; y1 -= pad; x2 += pad; y2 += pad
            if x1 <= x <= x2 and y1 <= y <= y2:
                hit = L
                break
        if hit:
            self.select_layer(hit['id'])
            self.dragging = True
            # compute drag offset
            if hit['type'] == 'text':
                self.drag_offset = (x - hit['x'], y - hit['y'])
            else:
                # store offset between click and bbox top-left
                bx, by = hit['bbox'][0], hit['bbox'][1]
                self.drag_offset = (x - bx, y - by)
        else:
            # clicked empty area: deselect
            self.deselect_layer()

    def _img_mouse_move(self, ev):
        if not self.dragging or not self.selected_layer_id:
            return
        pos = ev.pos()
        img_pos = self.to_image_coords(pos)
        if img_pos is None:
            return
        x, y = img_pos
        L = self._get_layer(self.selected_layer_id)
        if not L:
            return
        if L['type'] == 'text':
            # move center to mouse - offset
            dx, dy = self.drag_offset
            L['x'] = x - dx
            L['y'] = y - dy
        else:
            dx, dy = self.drag_offset
            w = L['bbox'][2] - L['bbox'][0]
            h = L['bbox'][3] - L['bbox'][1]
            new_x1 = x - dx
            new_y1 = y - dy
            new_bbox = (new_x1, new_y1, new_x1 + w, new_y1 + h)
            L['bbox'] = tuple(int(v) for v in new_bbox)
        self.update_display()

    def _img_mouse_release(self, ev):
        self.dragging = False
        # keep selection active
        self.reset_hide_timer()

    # ---------------- Rendering ----------------
    def update_display(self):
        # Start from working (base baked) image
        canvas = self.working.copy()
        draw = ImageDraw.Draw(canvas)
        # draw layers in order
        for L in self.layers:
            if L['type'] == 'text':
                try:
                    fnt = ImageFont.truetype("DejaVuSans.ttf", L['font_size'])
                except Exception:
                    fnt = ImageFont.load_default()
                color = L.get('color', self.default_text_color)
                # anchor center: PIL draws from top-left; if anchor center, calculate
                bbox = draw.textbbox((L['x'], L['y']), L['text'], font=fnt)
                tx1, ty1, tx2, ty2 = bbox
                # If anchor center, we treat L['x'],L['y'] as center and offset
                cx, cy = L['x'], L['y']
                w_t = tx2 - tx1
                h_t = ty2 - ty1
                draw.text((cx - w_t // 2, cy - h_t // 2), L['text'], font=fnt, fill=tuple(color))
                # draw selection rectangle if selected
                if self.selected_layer_id == L['id']:
                    rect = (cx - w_t // 2, cy - h_t // 2, cx + w_t // 2, cy + h_t // 2)
                    draw.rectangle(rect, outline=(255,255,0,180), width=2)
            else:  # shape
                x1, y1, x2, y2 = L['bbox']
                stroke = L.get('stroke', 3)
                stroke_col = L.get('stroke_color', self.default_stroke)
                fill = L.get('fill_color', self.default_fill)
                s = L.get('shape', 'rectangle')
                if s == 'rectangle':
                    if fill and fill[3] != 0:
                        draw.rectangle([x1,y1,x2,y2], fill=tuple(fill))
                    draw.rectangle([x1,y1,x2,y2], outline=tuple(stroke_col), width=stroke)
                elif s == 'ellipse':
                    if fill and fill[3] != 0:
                        draw.ellipse([x1,y1,x2,y2], fill=tuple(fill))
                    draw.ellipse([x1,y1,x2,y2], outline=tuple(stroke_col), width=stroke)
                elif s == 'line':
                    draw.line([x1,y1,x2,y2], fill=tuple(stroke_col), width=stroke)
                if self.selected_layer_id == L['id']:
                    draw.rectangle([x1-4, y1-4, x2+4, y2+4], outline=(255,255,0,180), width=2)

        # show on label scaled to fit
        pix = pil_to_qpixmap(canvas)
        screen_rect = QApplication.primaryScreen().availableGeometry()
        max_w = self.image_label.width() if self.image_label.width() > 10 else screen_rect.width()
        max_h = self.image_label.height() if self.image_label.height() > 10 else screen_rect.height() - 120
        scaled = pix.scaled(max_w, max_h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.image_label.setPixmap(scaled)

    # ---------------- Apply / Bake layers ----------------
    def apply_selected_text(self):
        L = self._get_layer(self.selected_layer_id)
        if not L or L['type'] != 'text':
            QMessageBox.information(self, "No text selected", "Select a text layer to apply.")
            return
        # draw onto working image and remove layer
        draw = ImageDraw.Draw(self.working)
        try:
            fnt = ImageFont.truetype("DejaVuSans.ttf", L['font_size'])
        except Exception:
            fnt = ImageFont.load_default()
        text = L['text']
        color = L.get('color', self.default_text_color)
        # compute top-left from center coords
        bbox = draw.textbbox((L['x'], L['y']), text, font=fnt)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        top_left = (L['x'] - tw // 2, L['y'] - th // 2)
        draw.text(top_left, text, font=fnt, fill=tuple(color))
        # remove layer
        self.layers = [li for li in self.layers if li['id'] != L['id']]
        self.selected_layer_id = None
        self.update_display()
        self.reset_hide_timer()

    def apply_selected_shape(self):
        L = self._get_layer(self.selected_layer_id)
        if not L or L['type'] != 'shape':
            QMessageBox.information(self, "No shape selected", "Select a shape layer to apply.")
            return
        draw = ImageDraw.Draw(self.working)
        x1,y1,x2,y2 = L['bbox']
        stroke = L.get('stroke', 3)
        stroke_col = L.get('stroke_color', self.default_stroke)
        fill = L.get('fill_color', self.default_fill)
        s = L.get('shape', 'rectangle')
        if s == 'rectangle':
            if fill and fill[3] != 0:
                draw.rectangle([x1,y1,x2,y2], fill=tuple(fill))
            draw.rectangle([x1,y1,x2,y2], outline=tuple(stroke_col), width=stroke)
        elif s == 'ellipse':
            if fill and fill[3] != 0:
                draw.ellipse([x1,y1,x2,y2], fill=tuple(fill))
            draw.ellipse([x1,y1,x2,y2], outline=tuple(stroke_col), width=stroke)
        elif s == 'line':
            draw.line([x1,y1,x2,y2], fill=tuple(stroke_col), width=stroke)
        # remove layer
        self.layers = [li for li in self.layers if li['id'] != L['id']]
        self.selected_layer_id = None
        self.update_display()
        self.reset_hide_timer()

    # ---------------- Image transforms ----------------
    def rotate90(self):
        # rotate working + all layer coordinates
        self.working = self.working.rotate(-90, expand=True)
        w, h = self.working.size
        # transform layers
        for L in self.layers:
            if L['type'] == 'text':
                x, y = L['x'], L['y']
                L['x'], L['y'] = y, (self.working.size[1] - x)
            else:
                x1, y1, x2, y2 = L['bbox']
                L['bbox'] = (y1, self.working.size[1] - x2, y2, self.working.size[1] - x1)
        # base image rotated as well
        self.base_image = self.base_image.rotate(-90, expand=True)
        self.update_display()
        self.reset_hide_timer()

    def negative(self):
        r, g, b, a = self.working.split()
        rgb = Image.merge("RGB", (r, g, b))
        neg = ImageOps.invert(rgb)
        self.working = Image.merge("RGBA", (*neg.split(), a))
        self.update_display()
        self.reset_hide_timer()

    def blackwhite(self):
        bw = ImageOps.grayscale(self.working.convert("RGB")).convert("RGBA")
        self.working = bw
        self.update_display()
        self.reset_hide_timer()

    # ---------------- Color dialogs ----------------
    def choose_text_color(self):
        c = QColorDialog.getColor()
        if c.isValid():
            color = (c.red(), c.green(), c.blue(), c.alpha())
            if self.selected_layer_id:
                L = self._get_layer(self.selected_layer_id)
                if L and L['type'] == 'text':
                    L['color'] = color
                else:
                    self.default_text_color = color
            else:
                self.default_text_color = color
            self.update_display()
            self.reset_hide_timer()

    def choose_fill_color(self):
        c = QColorDialog.getColor()
        if c.isValid():
            col = (c.red(), c.green(), c.blue(), c.alpha())
            if self.selected_layer_id:
                L = self._get_layer(self.selected_layer_id)
                if L and L['type'] == 'shape':
                    L['fill_color'] = col
                else:
                    self.default_fill = col
            else:
                self.default_fill = col
            self.update_display()
            self.reset_hide_timer()

    def choose_stroke_color(self):
        c = QColorDialog.getColor()
        if c.isValid():
            col = (c.red(), c.green(), c.blue(), c.alpha())
            if self.selected_layer_id:
                L = self._get_layer(self.selected_layer_id)
                if L and L['type'] == 'shape':
                    L['stroke_color'] = col
                else:
                    self.default_stroke = col
            else:
                self.default_stroke = col
            self.update_display()
            self.reset_hide_timer()

    # ---------------- Save operations ----------------
    def save_overwrite(self):
        try:
            # bake all layers into a copy and overwrite original
            final = self.working.copy()
            draw = ImageDraw.Draw(final)
            for L in self.layers:
                if L['type'] == 'text':
                    try:
                        fnt = ImageFont.truetype("DejaVuSans.ttf", L['font_size'])
                    except Exception:
                        fnt = ImageFont.load_default()
                    bbox = draw.textbbox((L['x'], L['y']), L['text'], font=fnt)
                    tw = bbox[2] - bbox[0]; th = bbox[3] - bbox[1]
                    tl = (L['x'] - tw // 2, L['y'] - th // 2)
                    draw.text(tl, L['text'], font=fnt, fill=tuple(L.get('color', self.default_text_color)))
                else:
                    x1,y1,x2,y2 = L['bbox']
                    stroke = L.get('stroke', 3)
                    stroke_col = L.get('stroke_color', self.default_stroke)
                    fill = L.get('fill_color', self.default_fill)
                    s = L.get('shape', 'rectangle')
                    if s == 'rectangle':
                        if fill and fill[3] != 0:
                            draw.rectangle([x1,y1,x2,y2], fill=tuple(fill))
                        draw.rectangle([x1,y1,x2,y2], outline=tuple(stroke_col), width=stroke)
                    elif s == 'ellipse':
                        if fill and fill[3] != 0:
                            draw.ellipse([x1,y1,x2,y2], fill=tuple(fill))
                        draw.ellipse([x1,y1,x2,y2], outline=tuple(stroke_col), width=stroke)
                    else:  # line
                        draw.line([x1,y1,x2,y2], fill=tuple(stroke_col), width=stroke)
            final_rgb = final.convert("RGB")
            final_rgb.save(self.image_path)
            # update working/base and clear layers
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
            final = self.working.copy()
            draw = ImageDraw.Draw(final)
            for L in self.layers:
                if L['type'] == 'text':
                    try:
                        fnt = ImageFont.truetype("DejaVuSans.ttf", L['font_size'])
                    except Exception:
                        fnt = ImageFont.load_default()
                    bbox = draw.textbbox((L['x'], L['y']), L['text'], font=fnt)
                    tw = bbox[2] - bbox[0]; th = bbox[3] - bbox[1]
                    tl = (L['x'] - tw // 2, L['y'] - th // 2)
                    draw.text(tl, L['text'], font=fnt, fill=tuple(L.get('color', self.default_text_color)))
                else:
                    x1,y1,x2,y2 = L['bbox']
                    stroke = L.get('stroke', 3)
                    stroke_col = L.get('stroke_color', self.default_stroke)
                    fill = L.get('fill_color', self.default_fill)
                    s = L.get('shape', 'rectangle')
                    if s == 'rectangle':
                        if fill and fill[3] != 0:
                            draw.rectangle([x1,y1,x2,y2], fill=tuple(fill))
                        draw.rectangle([x1,y1,x2,y2], outline=tuple(stroke_col), width=stroke)
                    elif s == 'ellipse':
                        if fill and fill[3] != 0:
                            draw.ellipse([x1,y1,x2,y2], fill=tuple(fill))
                        draw.ellipse([x1,y1,x2,y2], outline=tuple(stroke_col), width=stroke)
                    else:  # line
                        draw.line([x1,y1,x2,y2], fill=tuple(stroke_col), width=stroke)
            ext = os.path.splitext(self.image_path)[1].lower()
            fname = f"photo_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}{ext}"
            fpath = os.path.join(PHOTO_FOLDER, fname)
            ensure_folder()
            final.convert("RGB").save(fpath)
            if self.on_saved_callback:
                self.on_saved_callback()
            QMessageBox.information(self, "Saved As New", f"Saved new file: {fpath}")
            self.update_display()
        except Exception as e:
            QMessageBox.warning(self, "Save failed", str(e))

    # ---------------- Toolbar auto-hide helpers ----------------
    def reset_hide_timer(self):
        self.toolbar.show()
        self.hide_timer.start()

    def hide_toolbar(self):
        self.toolbar.hide()

    # show toolbar on any mouse move within dialog
    def mouseMoveEvent(self, ev):
        self.reset_hide_timer()
        return super().mouseMoveEvent(ev)

    # ensure toolbar shows on any keypress
    def keyPressEvent(self, ev):
        self.reset_hide_timer()
        if ev.key() == Qt.Key.Key_Escape:
            self.close()
        return super().keyPressEvent(ev)


# ---------------- Main gallery plugin ----------------
class PhotoGalleryPlugin(QWidget):
    def __init__(self, parent=None, apps=None, cfg=None):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle("Photo Gallery")
        # Keep plugin window resizable / adaptable (user removed strict fixed)
        self.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
        ensure_folder()
        self.init_ui()
        self.load_thumbnails()

    def init_ui(self):
        main_l = QVBoxLayout(self)
        self.setLayout(main_l)

        # Scroll area for thumbnails
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        content = QWidget()
        self.grid = QGridLayout(content)
        self.scroll.setWidget(content)
        main_l.addWidget(self.scroll)

        # Enable touch gestures / accept touch events
        self.scroll.viewport().setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents, True)
        self.scroll.grabGesture(Qt.GestureType.PanGesture)
        # set event handler for gesture
        self.scroll.event = self._touch_scroll_event

        # Bottom controls
        btn_bar = QHBoxLayout()
        btn_refresh = QPushButton("Refresh")
        btn_refresh.clicked.connect(self.load_thumbnails)
        btn_bar.addWidget(btn_refresh)
        btn_import = QPushButton("Import...")
        btn_import.clicked.connect(self.import_image)
        btn_bar.addWidget(btn_import)
        btn_open = QPushButton("Open Folder")
        btn_open.clicked.connect(self.open_folder)
        btn_bar.addWidget(btn_open)
        main_l.addLayout(btn_bar)

    def _touch_scroll_event(self, event):
        if event.type() == event.Type.Gesture:
            gesture = event.gesture(Qt.GestureType.PanGesture)
            if gesture:
                bar = self.scroll.verticalScrollBar()
                bar.setValue(bar.value() - gesture.delta().y())
                return True
        return super().event(event)

    def load_thumbnails(self):
        # clear grid
        while self.grid.count():
            it = self.grid.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        # load files
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

            caption = QLabel(fname)
            caption.setStyleSheet("color:white; font-size:10pt;")
            caption.setAlignment(Qt.AlignmentFlag.AlignCenter)

            container = QWidget()
            v = QVBoxLayout(container)
            v.addWidget(lbl)
            v.addWidget(caption)
            self.grid.addWidget(container, row, col)
            col += 1
            if col >= cols:
                col = 0; row += 1

    def open_editor(self, image_path):
        dlg = ImageEditorDialog(image_path, parent=self, on_saved_callback=self.load_thumbnails)
        dlg.exec()
        # ensure gallery refreshed after dialog closes (in case user canceled)
        self.load_thumbnails()

    def import_image(self):
        fpath, _ = QFileDialog.getOpenFileName(self, "Import Image", "", "Images (*.png *.jpg *.jpeg *.bmp *.gif)")
        if not fpath:
            return
        try:
            ext = os.path.splitext(fpath)[1].lower()
            fname = f"photo_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}{ext}"
            dst = os.path.join(PHOTO_FOLDER, fname)
            ensure_folder()
            with open(fpath, "rb") as fr, open(dst, "wb") as fw:
                fw.write(fr.read())
            QMessageBox.information(self, "Imported", f"Imported to {dst}")
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


# ---------------- Standalone test ----------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = PhotoGalleryPlugin()
    w.show()
    sys.exit(app.exec())
