import os

import cv2
import numpy as np
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QFrame,
    QTabWidget, QFileDialog, QSizePolicy, QTreeWidget
)
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtCore import Qt

from ui.image_panel import ImagePanel
from ui.tools_panel import ToolsPanel
from ui.directory_panel import DirectoryPanel


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle('Viewfinder')
        self.setMinimumSize(1100, 700)
        self.resize(1280, 800)

        self.img_current   = None   # always a BGR numpy array
        self.history       = []     # list of img_current copies for undo
        self.image_list    = []     # flat list of image paths (arrow navigation)
        self.current_index = -1
        self.roi_mask           = None   # np.ndarray (H, W) uint8 or None (= whole image)
        self._active_tool       = 'none' # currently open tool: 'grayscale' | 'blur' | 'none'
        self._brush_blurred_ref = None   # precomputed blur reference for brush strokes
        self._brush_gray_ref    = None   # precomputed greyscale reference for brush strokes

        central = QWidget()
        self.setCentralWidget(central)

        ly_main = QHBoxLayout(central)
        ly_main.setContentsMargins(0, 0, 0, 0)
        ly_main.setSpacing(0)

        # Left panel
        self.tab_widget  = QTabWidget()
        self.tab_widget.setFixedWidth(220)
        self.tools_panel = ToolsPanel()
        self.dir_panel   = DirectoryPanel()
        self.tab_widget.addTab(self.tools_panel, 'Tools')
        self.tab_widget.addTab(self.dir_panel,   'Directory')
        ly_main.addWidget(self.tab_widget)

        # Visual separator between the left panel and the image viewer
        separator = QFrame()
        separator.setFrameShape(QFrame.VLine)
        separator.setFrameShadow(QFrame.Sunken)
        ly_main.addWidget(separator)

        # Right panel — image viewer
        self.image_panel = ImagePanel()
        self.image_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        ly_main.addWidget(self.image_panel, stretch=1)

        # Menu bar
        self._build_menu()

        # Keyboard shortcuts
        self.shortcut_undo = QShortcut(QKeySequence('Ctrl+Z'), self)
        self.shortcut_undo.activated.connect(self.undo_action)

        self.shortcut_select_all = QShortcut(QKeySequence('Ctrl+A'), self)
        self.shortcut_select_all.activated.connect(self._select_all)

        # Esc: cancel in-progress polygon on first press, clear committed ROI on second
        self.shortcut_esc = QShortcut(QKeySequence(Qt.Key_Escape), self)
        self.shortcut_esc.activated.connect(self._on_escape)

        # Arrow-key navigation
        self.shortcut_prev = QShortcut(QKeySequence(Qt.Key_Left), self)
        self.shortcut_prev.activated.connect(lambda: self._navigate_if_not_tree(-1))

        self.shortcut_next = QShortcut(QKeySequence(Qt.Key_Right), self)
        self.shortcut_next.activated.connect(lambda: self._navigate_if_not_tree(1))

        # Signal connections — tools panel
        self.tools_panel.grayscale_requested.connect(self.apply_grayscale)
        self.tools_panel.blur_requested.connect(self.apply_blur)
        self.tools_panel.active_tool_changed.connect(self._on_tool_changed)
        self.tools_panel.roi_mode_changed.connect(self._on_roi_mode_changed)

        # Signal connections — image label ROI drawing
        self.image_panel.lb_image.roi_rect_selected.connect(self._on_roi_rect_set)
        self.image_panel.lb_image.roi_circle_selected.connect(self._on_roi_circle_set)
        self.image_panel.lb_image.roi_polygon_selected.connect(self._on_roi_polygon_set)
        self.image_panel.lb_image.brush_stroke.connect(self._on_brush_stroke)

        # Keep brush cursor size in sync with the slider
        self.tools_panel.slider_brush_size.valueChanged.connect(self._sync_brush_radius)

        self.dir_panel.file_selected.connect(self.load_image_from_path)


    def _build_menu(self):
        menu_bar  = self.menuBar()
        file_menu = menu_bar.addMenu('File')

        open_action = QAction('Open Image', self)
        open_action.setShortcut(QKeySequence('Ctrl+O'))
        open_action.triggered.connect(self.load_image)
        file_menu.addAction(open_action)

        open_dir_action = QAction('Open Directory', self)
        open_dir_action.setShortcut(QKeySequence('Ctrl+Shift+O'))
        open_dir_action.triggered.connect(self.load_directory)
        file_menu.addAction(open_dir_action)

        file_menu.addSeparator()

        save_action = QAction('Save', self)
        save_action.setShortcut(QKeySequence('Ctrl+S'))
        save_action.triggered.connect(self.save_image)
        file_menu.addAction(save_action)


    def load_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, 'Open Image', '',
            'Images (*.png *.jpg *.jpeg *.bmp *.tiff *.tif *.gif *.webp)'
        )
        if path:
            self.load_image_from_path(path)


    def load_directory(self):
        dir_path = QFileDialog.getExistingDirectory(self, 'Open Directory', '')
        if not dir_path:
            return

        self.image_list = self.dir_panel.get_all_images(dir_path)
        self.dir_panel.load_directory(dir_path)
        self.tab_widget.setCurrentWidget(self.dir_panel)

        if self.image_list:
            self.current_index = 0
            self.load_image_from_path(self.image_list[0])


    def load_image_from_path(self, path: str):
        img = cv2.imread(path)
        if img is None:
            print(f'Could not load image: {path}')
            return

        self.img_current = img
        self.history.clear()
        self._clear_roi()   # reset selection when switching to a new image

        if path in self.image_list:
            self.current_index = self.image_list.index(path)

        self.image_panel.set_image(self.img_current)
        self.dir_panel.highlight_file(path)
        self._update_title(path)


    def _navigate_if_not_tree(self, direction: int):
        """Navigate images — skipped when the directory tree has keyboard focus."""
        if isinstance(self.focusWidget(), QTreeWidget):
            return
        self._navigate(direction)


    def _navigate(self, direction: int):
        if not self.image_list or self.current_index < 0:
            return
        self.current_index = (self.current_index + direction) % len(self.image_list)
        self.load_image_from_path(self.image_list[self.current_index])


    def _update_title(self, path: str):
        name = os.path.basename(path)
        if self.image_list:
            self.setWindowTitle(
                f'Viewfinder  –  {self.current_index + 1}/{len(self.image_list)}  –  {name}'
            )
        else:
            self.setWindowTitle(f'Viewfinder  –  {name}')


    def _on_tool_changed(self, tool: str):
        """Track the active tool so the brush knows which effect to paint."""
        self._active_tool = tool


    def _on_roi_mode_changed(self, mode: str):
        """Activate the selected ROI drawing mode on the image panel."""
        self.image_panel.set_draw_mode(mode if mode != 'none' else None)
        self._sync_brush_radius()


    def _sync_brush_radius(self):
        """Copy the current brush-size slider value to InteractiveLabel."""
        self.image_panel.lb_image._brush_radius = self.tools_panel.get_brush_size()


    # ── ROI / Selection management ─────────────────────────────────────────────

    def _on_roi_rect_set(self, x: int, y: int, w: int, h: int):
        """Convert a drawn rectangle into an active selection mask."""
        if self.img_current is None or w == 0 or h == 0:
            return

        ratio_x, ratio_y = self._get_pixel_ratios()
        if ratio_x is None:
            return

        real_h, real_w = self.img_current.shape[:2]
        rx = max(0, int(x * ratio_x))
        ry = max(0, int(y * ratio_y))
        rw = min(int(w * ratio_x), real_w - rx)
        rh = min(int(h * ratio_y), real_h - ry)

        if rw <= 0 or rh <= 0:
            return

        mask = np.zeros((real_h, real_w), dtype=np.uint8)
        cv2.rectangle(mask, (rx, ry), (rx + rw, ry + rh), 255, -1)
        self._set_roi_mask(mask, {'type': 'rectangle', 'x': x, 'y': y, 'w': w, 'h': h})


    def _on_roi_circle_set(self, cx: int, cy: int, radius: int):
        """Convert a drawn circle into an active selection mask."""
        if self.img_current is None or radius == 0:
            return

        ratio_x, ratio_y = self._get_pixel_ratios()
        if ratio_x is None:
            return

        real_h, real_w = self.img_current.shape[:2]
        real_cx     = int(cx * ratio_x)
        real_cy     = int(cy * ratio_y)
        real_radius = int(radius * (ratio_x + ratio_y) / 2)

        mask = np.zeros((real_h, real_w), dtype=np.uint8)
        cv2.circle(mask, (real_cx, real_cy), real_radius, 255, -1)
        self._set_roi_mask(mask, {'type': 'circle', 'cx': cx, 'cy': cy, 'r': radius})


    def _on_roi_polygon_set(self, points: list):
        """Convert a drawn polygon into an active selection mask."""
        if self.img_current is None or len(points) < 3:
            return

        ratio_x, ratio_y = self._get_pixel_ratios()
        if ratio_x is None:
            return

        real_h, real_w = self.img_current.shape[:2]
        real_pts = np.array(
            [(int(x * ratio_x), int(y * ratio_y)) for x, y in points],
            dtype=np.int32
        )

        mask = np.zeros((real_h, real_w), dtype=np.uint8)
        cv2.fillPoly(mask, [real_pts], 255)
        self._set_roi_mask(mask, {'type': 'polygon', 'pts': points})


    def _set_roi_mask(self, mask: np.ndarray, shape_dict: dict):
        """Store the new selection mask and update the on-screen overlay and status label."""
        self.roi_mask = mask
        self.image_panel.lb_image.set_committed_roi(shape_dict)

        t = shape_dict['type']
        if t == 'rectangle':
            status = f"Rect {shape_dict['w']}×{shape_dict['h']}"
        elif t == 'circle':
            status = f"Circle r={shape_dict['r']}"
        elif t == 'polygon':
            status = f"Polygon ({len(shape_dict['pts'])} pts)"
        elif t == 'all':
            status = 'Full image'
        else:
            status = 'Custom'
        self.tools_panel.set_roi_status(status)


    def _clear_roi(self):
        """Clear the active selection — subsequent operations apply to the whole image."""
        self.roi_mask = None
        self.image_panel.lb_image.clear_roi_display()
        self.tools_panel.set_roi_status('None')
        # Also exit the current ROI drawing mode and uncheck all shape buttons
        self.tools_panel._deactivate_roi_buttons()


    def _on_escape(self):
        """Esc key handler — two-stage behaviour:
        1. If a polygon is being drawn, cancel it (vertices cleared).
        2. Otherwise clear the committed selection entirely.
        """
        lb = self.image_panel.lb_image
        if lb.draw_mode == 'polygon' and lb._polygon_points:
            lb._polygon_points.clear()
            lb._cursor_pos = None
            lb.update()
        else:
            self._clear_roi()


    def _get_active_mask(self) -> np.ndarray:
        """Return roi_mask if a selection is active, else a full-white (whole-image) mask."""
        if self.roi_mask is not None:
            return self.roi_mask
        h, w = self.img_current.shape[:2]
        return np.ones((h, w), dtype=np.uint8) * 255


    def _select_all(self):
        """Ctrl+A: select the entire image as the active ROI."""
        if self.img_current is None:
            return
        h, w = self.img_current.shape[:2]
        mask = np.ones((h, w), dtype=np.uint8) * 255
        self._set_roi_mask(mask, {'type': 'all'})


    # ── Image operations ───────────────────────────────────────────────────────

    def undo_action(self):
        if self.history:
            self.img_current = self.history.pop()
            self.image_panel.update_image(self.img_current)


    def apply_grayscale(self):
        """Convert to greyscale within the active selection (or the whole image)."""
        if self.img_current is None:
            return

        self.history.append(self.img_current.copy())

        mask       = self._get_active_mask()
        img_gray   = cv2.cvtColor(self.img_current, cv2.COLOR_BGR2GRAY)
        img_gray_3 = cv2.cvtColor(img_gray, cv2.COLOR_GRAY2BGR)
        self.img_current[mask == 255] = img_gray_3[mask == 255]
        self.image_panel.update_image(self.img_current)


    def apply_blur(self):
        """Apply Gaussian blur within the active selection (or the whole image)."""
        if self.img_current is None:
            return

        self.history.append(self.img_current.copy())

        mask    = self._get_active_mask()
        kernel  = self.tools_panel.get_blur_kernel()
        blurred = cv2.GaussianBlur(self.img_current, (kernel, kernel), 0)
        self.img_current[mask == 255] = blurred[mask == 255]
        self.image_panel.update_image(self.img_current)


    def _get_pixel_ratios(self):
        """Return (ratio_x, ratio_y) mapping display coords to real image coords.
        Returns (None, None) if no pixmap is currently shown."""
        pixmap = self.image_panel.lb_image.pixmap()
        if pixmap is None or pixmap.width() == 0 or pixmap.height() == 0:
            return None, None
        real_h, real_w = self.img_current.shape[:2]
        return real_w / pixmap.width(), real_h / pixmap.height()


    def _apply_mask_blur(self, mask: np.ndarray):
        """Apply Gaussian blur to img_current in-place, restricted to mask==255 pixels.
        Used internally by the brush blur tool."""
        kernel  = self.tools_panel.get_blur_kernel()
        blurred = cv2.GaussianBlur(self.img_current, (kernel, kernel), 0)
        self.img_current[mask == 255] = blurred[mask == 255]
        self.image_panel.refresh()


    def _on_brush_stroke(self, x: int, y: int, is_first_point: bool):
        """Dispatch a brush stroke to the method matching the active tool.

        The brush always paints with whichever tool is currently open in the
        tool options panel (Blur or Grayscale).  If no tool is selected the
        stroke is silently ignored.
        """
        if self._active_tool == 'blur':
            self.apply_blur_brush(x, y, is_first_point)
        elif self._active_tool == 'grayscale':
            self.apply_grayscale_brush(x, y, is_first_point)
        # else: no tool active — do nothing


    def apply_blur_brush(self, x: int, y: int, is_first_point: bool):

        """Apply blur under the brush cursor at position (x, y).

        is_first_point=True  → save history and precompute a blurred reference
                               image once for the entire stroke.
        is_first_point=False → copy pixels from the precomputed reference—
                               no repeated full-image GaussianBlur calls.
        """
        if self.img_current is None:
            return

        ratio_x, ratio_y = self._get_pixel_ratios()
        if ratio_x is None:
            return

        if is_first_point:
            self.history.append(self.img_current.copy())
            # Precompute the fully blurred version of the current image.
            # All brush dabs in this stroke copy from this snapshot,
            # so GaussianBlur is only called once per mouse-down event.
            kernel = self.tools_panel.get_blur_kernel()
            self._brush_blurred_ref = cv2.GaussianBlur(self.img_current, (kernel, kernel), 0)

        if self._brush_blurred_ref is None:
            return

        brush_display_r = self.tools_panel.get_brush_size()
        real_h, real_w  = self.img_current.shape[:2]
        # Scale brush radius from display space to image space
        real_cx = int(x * ratio_x)
        real_cy = int(y * ratio_y)
        real_r  = max(1, int(brush_display_r * (ratio_x + ratio_y) / 2))

        mask = np.zeros((real_h, real_w), dtype=np.uint8)
        cv2.circle(mask, (real_cx, real_cy), real_r, 255, -1)
        # Copy blurred pixels into img_current (no full re-blur on each dab)
        self.img_current[mask == 255] = self._brush_blurred_ref[mask == 255]
        self.image_panel.refresh()


    def apply_grayscale_brush(self, x: int, y: int, is_first_point: bool):
        """Paint greyscale under the brush cursor at position (x, y).

        is_first_point=True  → save history and precompute a greyscale reference
                               image once for the entire stroke.
        is_first_point=False → copy pixels from the precomputed reference.
        """
        if self.img_current is None:
            return

        ratio_x, ratio_y = self._get_pixel_ratios()
        if ratio_x is None:
            return

        if is_first_point:
            self.history.append(self.img_current.copy())
            # Precompute greyscale version once for the whole stroke
            img_gray           = cv2.cvtColor(self.img_current, cv2.COLOR_BGR2GRAY)
            self._brush_gray_ref = cv2.cvtColor(img_gray, cv2.COLOR_GRAY2BGR)

        if self._brush_gray_ref is None:
            return

        brush_display_r = self.tools_panel.get_brush_size()
        real_h, real_w  = self.img_current.shape[:2]
        real_cx = int(x * ratio_x)
        real_cy = int(y * ratio_y)
        real_r  = max(1, int(brush_display_r * (ratio_x + ratio_y) / 2))

        mask = np.zeros((real_h, real_w), dtype=np.uint8)
        cv2.circle(mask, (real_cx, real_cy), real_r, 255, -1)
        self.img_current[mask == 255] = self._brush_gray_ref[mask == 255]
        self.image_panel.refresh()


    def save_image(self):
        if self.img_current is None:
            print('First, load an image.')
            return

        path, _ = QFileDialog.getSaveFileName(
            self, 'Save Image', '',
            'Images (*.png *.jpg *.jpeg *.bmp)'
        )
        if path:
            cv2.imwrite(path, self.img_current)
