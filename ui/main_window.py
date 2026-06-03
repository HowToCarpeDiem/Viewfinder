import os

import cv2
import numpy as np
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QFrame,
    QTabWidget, QFileDialog, QSizePolicy, QTreeWidget,
    QDialog, QVBoxLayout, QLabel, QScrollArea, QDialogButtonBox
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
        self.history       = []     # undo stack — list of img_current copies
        self.redo_stack    = []     # redo stack — filled by undo, cleared by any edit
        self._adj_base     = None   # snapshot taken at the start of a live slider session
        self.image_list    = []     # flat list of image paths (arrow navigation)
        self.current_index = -1
        self.roi_mask           = None   # np.ndarray (H, W) uint8 or None (= whole image)
        self._active_tool       = 'none' # currently open tool: 'adjustments' | 'blur' | 'none'
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

        self.shortcut_redo = QShortcut(QKeySequence('Ctrl+Y'), self)
        self.shortcut_redo.activated.connect(self.redo_action)

        self.shortcut_invert_roi = QShortcut(QKeySequence('Ctrl+I'), self)
        self.shortcut_invert_roi.activated.connect(self.invert_roi)

        self.shortcut_crop = QShortcut(QKeySequence('Ctrl+K'), self)
        self.shortcut_crop.activated.connect(self.crop_to_selection)

        self.shortcut_cut = QShortcut(QKeySequence('Ctrl+X'), self)
        self.shortcut_cut.activated.connect(self.cut_selection)

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
        self.tools_panel.adj_session_start.connect(self._on_adj_session_start)
        self.tools_panel.brightness_live.connect(self._on_brightness_live)
        self.tools_panel.contrast_live.connect(self._on_contrast_live)
        self.tools_panel.saturation_live.connect(self._on_saturation_live)
        # End each slider session when the user releases the slider
        for sl in (
            self.tools_panel.slider_brightness,
            self.tools_panel.slider_contrast,
            self.tools_panel.slider_saturation,
        ):
            sl.sliderReleased.connect(self._on_adj_session_end)
        self.tools_panel.blur_requested.connect(self.apply_blur)
        self.tools_panel.transform_requested.connect(self.apply_transform)
        self.tools_panel.active_tool_changed.connect(self._on_tool_changed)
        self.tools_panel.roi_mode_changed.connect(self._on_roi_mode_changed)

        # Signal connections — image label ROI drawing
        self.image_panel.lb_image.roi_rect_selected.connect(self._on_roi_rect_set)
        self.image_panel.lb_image.roi_circle_selected.connect(self._on_roi_circle_set)
        self.image_panel.lb_image.roi_polygon_selected.connect(self._on_roi_polygon_set)
        self.image_panel.lb_image.brush_stroke.connect(self._on_brush_stroke)
        self.image_panel.lb_image.roi_move_delta.connect(self._on_roi_move)

        # Keep brush cursor size in sync with the slider
        self.tools_panel.slider_brush_size.valueChanged.connect(self._sync_brush_radius)

        # Image info panel — update on zoom/resize (render_done) and on pan (scrollbars)
        self.image_panel.render_done.connect(self._update_image_info)
        self.image_panel.horizontalScrollBar().valueChanged.connect(self._update_image_info)
        self.image_panel.verticalScrollBar().valueChanged.connect(self._update_image_info)

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

        settings_menu = menu_bar.addMenu('Settings')

        shortcuts_action = QAction('Shortcuts', self)
        shortcuts_action.setShortcut(QKeySequence('Ctrl+/'))
        shortcuts_action.triggered.connect(self._show_shortcuts_dialog)
        settings_menu.addAction(shortcuts_action)


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
        self.redo_stack.clear()
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


    def _update_image_info(self):
        """Refresh the image info panel (resolution + visible viewport coords).

        Called whenever the display changes: zoom, resize, pan, or new image.
        """
        if self.img_current is None:
            self.tools_panel.set_image_info(None, None)
            return

        h, w = self.img_current.shape[:2]
        coords = self.image_panel.get_viewport_image_coords()
        self.tools_panel.set_image_info((w, h), coords)


    def _on_roi_move(self, dx_display: int, dy_display: int):
        """Ctrl+RMB drag: translate the active ROI mask and its visual overlay.

        dx_display / dy_display are deltas in display (pixmap) pixels.
        They are converted to image pixels using the current pixmap-to-image ratio.
        The mask is shifted with cv2.warpAffine so there is no wrap-around —
        pixels that leave the image boundary become unselected (0).
        """
        if self.roi_mask is None or self.img_current is None:
            return

        pm = self.image_panel.lb_image.pixmap()
        if pm is None or pm.width() == 0 or pm.height() == 0:
            return

        img_h, img_w = self.img_current.shape[:2]
        pm_w, pm_h   = pm.width(), pm.height()

        # Convert display-pixel delta → image-pixel delta
        dx_img = int(round(dx_display * img_w / pm_w))
        dy_img = int(round(dy_display * img_h / pm_h))

        if dx_img == 0 and dy_img == 0:
            return

        # Translate the mask (no wrap-around; out-of-bounds pixels become 0)
        M = np.float32([[1, 0, dx_img], [0, 1, dy_img]])
        self.roi_mask = cv2.warpAffine(
            self.roi_mask, M, (img_w, img_h),
            flags=cv2.INTER_NEAREST,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=0,
        )

        # Shift the visual overlay in normalised coordinates
        dx_norm = dx_display / pm_w
        dy_norm = dy_display / pm_h
        self.image_panel.lb_image.shift_committed_roi(dx_norm, dy_norm)


    #ROI / Selection management

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
        self.tools_panel.reset_adjustment_sliders()


    def _clear_roi(self):
        """Clear the active selection — subsequent operations apply to the whole image."""
        self.roi_mask = None
        self.image_panel.lb_image.clear_roi_display()
        self.tools_panel.set_roi_status('None')
        self.tools_panel.reset_adjustment_sliders()
        # Also exit the current ROI drawing mode and uncheck all shape buttons
        self.tools_panel._deactivate_roi_buttons()


    def _on_escape(self):
        """Esc key handler — two-stage behaviour:
        1. If a polygon is being drawn, cancel it (vertices cleared).
        2. Otherwise clear the committed selection entirely.
        """
        lb = self.image_panel.lb_image
        if lb.draw_mode == 'polygon' and lb._polygon_pts_n:
            lb._polygon_pts_n.clear()
            lb._cursor_pos_n = None
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


    def invert_roi(self):
        """Ctrl+I: flip selected / unselected pixels (bitwise NOT on roi_mask).

        Has no effect when no selection is active.  The shape outline is kept
        and the full-image border is added so the user can see both boundaries
        of the newly selected region (everything outside the original shape).
        Calling Ctrl+I a second time reverts back to the original selection.
        """
        if self.roi_mask is None:
            return
        self.roi_mask = cv2.bitwise_not(self.roi_mask)
        # Toggle the visual: keep shape outline, add/remove the image border
        self.image_panel.lb_image.invert_roi_display()
        # Toggle status label: 'Rect 120×80' ↔ 'Inverted Rect 120×80'
        current = self.tools_panel.lbl_roi_status.text()
        if current.startswith('Inverted '):
            self.tools_panel.set_roi_status(current[len('Inverted '):])
        else:
            self.tools_panel.set_roi_status(f'Inverted {current}')


    # Image operations

    def undo_action(self):
        """Ctrl+Z: revert to the previous image state."""
        if self.history:
            self.redo_stack.append(self.img_current.copy())
            self.img_current = self.history.pop()
            self.image_panel.update_image(self.img_current)


    def redo_action(self):
        """Ctrl+Y: re-apply the last undone edit."""
        if self.redo_stack:
            self.history.append(self.img_current.copy())
            self.img_current = self.redo_stack.pop()
            self.image_panel.update_image(self.img_current)


    def _push_history(self):
        """Save the current image to the undo stack and wipe the redo stack.
        Must be called exactly once before every destructive edit."""
        self.history.append(self.img_current.copy())
        self.redo_stack.clear()


    def _bgr_view(self) -> np.ndarray:
        """Return a (possibly writable) view of only the BGR channels.

        Works transparently for both BGR (3-ch) and BGRA (4-ch) images.
        Write operations on the returned slice propagate back to img_current.
        """
        return self.img_current[:, :, :3]


    # Live adjustment helpers

    def _on_adj_session_start(self):
        """Called when any adjustment slider is first grabbed (sliderPressed).

        Saves a snapshot of the current image as the base for this editing
        session and pushes one undo entry.  If a session is already open
        (e.g. user grabbed two sliders simultaneously) the second press is
        ignored so history is only pushed once.
        """
        if self.img_current is None or self._adj_base is not None:
            return
        self._push_history()
        self._adj_base = self.img_current.copy()

    def _on_adj_session_end(self):
        """Called when an adjustment slider is released — closes the session."""
        self._adj_base = None

    def _on_brightness_live(self, value: int):
        """Apply brightness offset to _adj_base and stream to display."""
        if self._adj_base is None or self.img_current is None:
            return
        result  = self._adj_base.copy()
        bgr     = result[:, :, :3]
        mask    = self._get_active_mask()
        adjusted = np.clip(bgr.astype(np.int16) + value, 0, 255).astype(np.uint8)
        bgr[mask == 255] = adjusted[mask == 255]
        self.img_current = result
        self.image_panel.update_image(result)

    def _on_contrast_live(self, value: int):
        """Apply contrast scaling to _adj_base and stream to display."""
        if self._adj_base is None or self.img_current is None:
            return
        result  = self._adj_base.copy()
        bgr     = result[:, :, :3]
        mask    = self._get_active_mask()
        alpha_f = 1.0 + value / 100.0
        adjusted = cv2.convertScaleAbs(bgr, alpha=alpha_f, beta=0)
        bgr[mask == 255] = adjusted[mask == 255]
        self.img_current = result
        self.image_panel.update_image(result)

    def _on_saturation_live(self, value: int):
        """Apply saturation scaling to _adj_base and stream to display."""
        if self._adj_base is None or self.img_current is None:
            return
        result  = self._adj_base.copy()
        bgr     = result[:, :, :3]
        mask    = self._get_active_mask()
        scale   = 1.0 + value / 100.0
        img_hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV).astype(np.float32)
        img_hsv[:, :, 1] = np.clip(img_hsv[:, :, 1] * scale, 0, 255)
        adjusted = cv2.cvtColor(img_hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)
        bgr[mask == 255] = adjusted[mask == 255]
        self.img_current = result
        self.image_panel.update_image(result)


    def apply_grayscale(self):
        """Convert to greyscale within the active selection (or the whole image)."""
        if self.img_current is None:
            return

        self._push_history()

        mask       = self._get_active_mask()
        bgr        = self._bgr_view()
        img_gray   = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        img_gray_3 = cv2.cvtColor(img_gray, cv2.COLOR_GRAY2BGR)
        bgr[mask == 255] = img_gray_3[mask == 255]
        self.image_panel.update_image(self.img_current)


    def apply_brightness(self):
        """Shift pixel brightness within the active selection.

        Value comes from tools_panel.get_brightness() (-100 … +100).
        Positive values brighten, negative values darken.
        """
        if self.img_current is None:
            return
        value = self.tools_panel.get_brightness()
        if value == 0:
            return

        self._push_history()
        mask     = self._get_active_mask()
        bgr      = self._bgr_view()
        adjusted = np.clip(bgr.astype(np.int16) + value, 0, 255).astype(np.uint8)
        bgr[mask == 255] = adjusted[mask == 255]
        self.image_panel.update_image(self.img_current)


    def apply_contrast(self):
        """Scale pixel contrast within the active selection.

        Value comes from tools_panel.get_contrast() (-100 … +100).
        0 = no change; positive = more contrast; negative = less contrast.
        Alpha factor = 1 + value/100 (range 0.0 – 2.0).
        """
        if self.img_current is None:
            return
        value = self.tools_panel.get_contrast()
        if value == 0:
            return

        self._push_history()
        mask    = self._get_active_mask()
        bgr     = self._bgr_view()
        alpha_f = 1.0 + value / 100.0
        # convertScaleAbs: dst = saturate(|alpha * src + beta|)
        adjusted = cv2.convertScaleAbs(bgr, alpha=alpha_f, beta=0)
        bgr[mask == 255] = adjusted[mask == 255]
        self.image_panel.update_image(self.img_current)


    def apply_saturation(self):
        """Scale colour saturation within the active selection.

        Value comes from tools_panel.get_saturation() (-100 … +100).
        0 = no change; +100 = double saturation; -100 = fully desaturated.
        Scale factor = 1 + value/100 (range 0.0 – 2.0), applied to the S
        channel in HSV space.
        """
        if self.img_current is None:
            return
        value = self.tools_panel.get_saturation()
        if value == 0:
            return

        self._push_history()
        mask    = self._get_active_mask()
        bgr     = self._bgr_view()
        scale   = 1.0 + value / 100.0
        img_hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV).astype(np.float32)
        img_hsv[:, :, 1] = np.clip(img_hsv[:, :, 1] * scale, 0, 255)
        adjusted = cv2.cvtColor(img_hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)
        bgr[mask == 255] = adjusted[mask == 255]
        self.image_panel.update_image(self.img_current)


    def apply_blur(self):
        """Apply Gaussian blur within the active selection (or the whole image)."""
        if self.img_current is None:
            return

        self._push_history()

        mask    = self._get_active_mask()
        bgr     = self._bgr_view()
        kernel  = self.tools_panel.get_blur_kernel()
        blurred = cv2.GaussianBlur(bgr, (kernel, kernel), 0)
        bgr[mask == 255] = blurred[mask == 255]
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
        bgr     = self._bgr_view()
        kernel  = self.tools_panel.get_blur_kernel()
        blurred = cv2.GaussianBlur(bgr, (kernel, kernel), 0)
        bgr[mask == 255] = blurred[mask == 255]
        self.image_panel.refresh()


    def _on_brush_stroke(self, x: int, y: int, is_first_point: bool):
        """Dispatch a brush stroke to the method matching the active tool.

        The brush always paints with whichever tool is currently open in the
        tool options panel (Blur or Adjustments/Grayscale).  If no tool is
        selected the stroke is silently ignored.
        """
        if self._active_tool == 'blur':
            self.apply_blur_brush(x, y, is_first_point)
        elif self._active_tool == 'adjustments':
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
            self._push_history()
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
            self._push_history()
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


    def crop_to_selection(self):
        """Ctrl+K: crop the image to the bounding box of the active selection.

        For rectangular selections the result is a plain BGR crop.
        For circles and polygons the region outside the mask is made
        transparent (BGRA with alpha=0), and the image is then cropped
        to the tight bounding box of the shape.
        Has no effect when no selection is active.
        """
        if self.img_current is None or self.roi_mask is None:
            return

        # Find the tight bounding box of all selected pixels
        ys, xs = np.where(self.roi_mask == 255)
        if len(ys) == 0:
            return  # empty mask — nothing to crop

        y1, y2 = int(ys.min()), int(ys.max()) + 1
        x1, x2 = int(xs.min()), int(xs.max()) + 1

        self._push_history()

        cropped      = self.img_current[y1:y2, x1:x2].copy()
        mask_cropped = self.roi_mask[y1:y2, x1:x2]

        # Check whether every pixel in the bounding box is selected
        is_fully_rect = bool(np.all(mask_cropped == 255))

        if not is_fully_rect:
            # Non-rectangular shape: add alpha, set 0 outside the mask
            if cropped.shape[2] == 3:
                cropped = cv2.cvtColor(cropped, cv2.COLOR_BGR2BGRA)
            cropped[:, :, 3] = mask_cropped

        self.img_current = cropped
        self._clear_roi()
        self.image_panel.set_image(self.img_current)


    def cut_selection(self):
        """Ctrl+X: make the selected area fully transparent (alpha = 0).

        The image is automatically converted to BGRA if it is currently BGR.
        Has no effect when no selection is active.
        """
        if self.img_current is None or self.roi_mask is None:
            return

        self._push_history()

        # Ensure we have an alpha channel
        if self.img_current.shape[2] == 3:
            self.img_current = cv2.cvtColor(self.img_current, cv2.COLOR_BGR2BGRA)

        # Zero-out alpha where the mask is selected
        self.img_current[:, :, 3][self.roi_mask == 255] = 0
        self.image_panel.update_image(self.img_current)


    def apply_transform(self, operation: str):
        """Apply a flip or rotation to the current image.

        Supported operations:
            flip_h      — mirror left ↔ right  (cv2.flip axis 1)
            flip_v      — mirror top  ↕ bottom (cv2.flip axis 0)
            rotate_cw   — 90° clockwise
            rotate_ccw  — 90° counter-clockwise
            rotate_180  — 180°

        The ROI mask is transformed together with the image for operations
        that preserve its shape (flip_h, flip_v, rotate_180).  For 90°
        rotations the mask is cleared because the image dimensions change.
        """
        if self.img_current is None:
            return

        self._push_history()

        if operation == 'flip_h':
            self.img_current = cv2.flip(self.img_current, 1)
            if self.roi_mask is not None:
                self.roi_mask = cv2.flip(self.roi_mask, 1)
                # Flip the visual overlay so it stays on the correct spot
                self.image_panel.lb_image.clear_roi_display()
                self.tools_panel.set_roi_status('Rect (flipped)')

        elif operation == 'flip_v':
            self.img_current = cv2.flip(self.img_current, 0)
            if self.roi_mask is not None:
                self.roi_mask = cv2.flip(self.roi_mask, 0)
                self.image_panel.lb_image.clear_roi_display()
                self.tools_panel.set_roi_status('Rect (flipped)')

        elif operation == 'rotate_cw':
            self.img_current = cv2.rotate(self.img_current, cv2.ROTATE_90_CLOCKWISE)
            self._clear_roi()   # 90° rotation changes image dimensions

        elif operation == 'rotate_ccw':
            self.img_current = cv2.rotate(self.img_current, cv2.ROTATE_90_COUNTERCLOCKWISE)
            self._clear_roi()

        elif operation == 'rotate_180':
            self.img_current = cv2.rotate(self.img_current, cv2.ROTATE_180)
            if self.roi_mask is not None:
                self.roi_mask = cv2.rotate(self.roi_mask, cv2.ROTATE_180)
                self.image_panel.lb_image.clear_roi_display()
                self.tools_panel.set_roi_status('Rect (rotated)')

        # set_image resets zoom — appropriate because rotation may change aspect ratio
        self.image_panel.set_image(self.img_current)


    def save_image(self):
        if self.img_current is None:
            print('First, load an image.')
            return

        path, _ = QFileDialog.getSaveFileName(
            self, 'Save Image', '',
            'PNG with transparency (*.png);;JPEG (*.jpg *.jpeg);;BMP (*.bmp)'
        )
        if not path:
            return

        img_to_save = self.img_current
        # If saving to a format that does not support alpha, flatten onto white
        ext = path.rsplit('.', 1)[-1].lower()
        if ext in ('jpg', 'jpeg', 'bmp') and img_to_save.shape[2] == 4:
            bg    = np.ones_like(img_to_save[:, :, :3], dtype=np.uint8) * 255
            alpha = img_to_save[:, :, 3:4].astype(np.float32) / 255.0
            bgr   = img_to_save[:, :, :3].astype(np.float32)
            flat  = (bgr * alpha + bg.astype(np.float32) * (1.0 - alpha))
            img_to_save = np.clip(flat, 0, 255).astype(np.uint8)

        cv2.imwrite(path, img_to_save)
    def _show_shortcuts_dialog(self):
        """Display a modal dialog listing all keyboard shortcuts."""
        dlg = QDialog(self)
        dlg.setWindowTitle('Keyboard Shortcuts')
        dlg.setMinimumWidth(480)

        ly = QVBoxLayout(dlg)
        ly.setSpacing(0)
        ly.setContentsMargins(16, 12, 16, 12)

        SECTIONS = [
            ('File', [
                ('Ctrl+O',           'Open image'),
                ('Ctrl+Shift+O',     'Open directory'),
                ('Ctrl+S',           'Save image'),
            ]),
            ('Navigation', [
                ('← / → Arrow keys',  'Previous / next image'),
            ]),
            ('Edit', [
                ('Ctrl+Z',           'Undo'),
                ('Ctrl+Y',           'Redo'),
            ]),
            ('Selection (ROI)', [
                ('Ctrl+A',           'Select all'),
                ('Ctrl+I',           'Invert selection'),
                ('Ctrl+K',           'Crop to selection'),
                ('Ctrl+X',           'Cut selection (make transparent)'),
                ('Esc',              'Cancel polygon  /  clear selection'),
                ('RMB click',        'Close polygon (no drag)'),
            ]),
            ('View', [
                ('Ctrl + Scroll',    'Zoom in / out'),
                ('RMB drag',         'Pan image'),
            ]),
            ('Other', [
                ('Ctrl+/',           'Show this shortcuts window'),
            ]),
        ]

        # Styles
        section_style = (
            'font-weight: bold; font-size: 12px;'
            'margin-top: 10px; margin-bottom: 2px; color: #222;'
        )
        row_key_style  = 'font-family: monospace; color: #1a73e8; min-width: 160px;'
        row_desc_style = 'color: #333;'
        sep_style      = 'color: #ccc; margin: 0;'

        for section_title, rows in SECTIONS:
            lbl_section = QLabel(section_title)
            lbl_section.setStyleSheet(section_style)
            ly.addWidget(lbl_section)

            sep = QLabel('─' * 55)
            sep.setStyleSheet(sep_style)
            ly.addWidget(sep)

            for key, desc in rows:
                row_widget = QWidget()
                row_layout = QHBoxLayout(row_widget)
                row_layout.setContentsMargins(4, 1, 4, 1)
                row_layout.setSpacing(8)

                lbl_key  = QLabel(key)
                lbl_key.setStyleSheet(row_key_style)
                lbl_desc = QLabel(desc)
                lbl_desc.setStyleSheet(row_desc_style)

                row_layout.addWidget(lbl_key)
                row_layout.addWidget(lbl_desc)
                row_layout.addStretch()
                ly.addWidget(row_widget)

        ly.addSpacing(12)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok)
        buttons.accepted.connect(dlg.accept)
        ly.addWidget(buttons)

        dlg.exec()
