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

        # Arrow-key navigatio
        self.shortcut_prev = QShortcut(QKeySequence(Qt.Key_Left), self)
        self.shortcut_prev.activated.connect(lambda: self._navigate_if_not_tree(-1))

        self.shortcut_next = QShortcut(QKeySequence(Qt.Key_Right), self)
        self.shortcut_next.activated.connect(lambda: self._navigate_if_not_tree(1))

        # Signal connections
        self.tools_panel.grayscale_requested.connect(self.apply_grayscale)
        self.tools_panel.active_tool_changed.connect(self._on_tool_changed)
        self.tools_panel.roi_mode_changed.connect(self._on_roi_mode_changed)

        self.image_panel.lb_image.roi_rect_selected.connect(self.apply_blur_rect)
        self.image_panel.lb_image.roi_circle_selected.connect(self.apply_blur_circle)
        self.image_panel.lb_image.roi_polygon_selected.connect(self.apply_blur_polygon)

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
        """Handle tool selection changes. ROI mode is managed separately via roi_mode_changed."""
        pass


    def _on_roi_mode_changed(self, mode: str):
        """Activate the selected ROI drawing mode on the image panel."""
        self.image_panel.set_draw_mode(mode if mode != 'none' else None)


    def undo_action(self):
        if self.history:
            self.img_current = self.history.pop()
            self.image_panel.update_image(self.img_current)

    def apply_grayscale(self):
        if self.img_current is None:
            return

        self.history.append(self.img_current.copy())

        img_gray = cv2.cvtColor(self.img_current, cv2.COLOR_BGR2GRAY)
        self.img_current = cv2.cvtColor(img_gray, cv2.COLOR_GRAY2BGR)
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
        """Apply Gaussian blur to img_current in-place, restricted to mask==255 pixels."""
        kernel  = self.tools_panel.get_blur_kernel()
        blurred = cv2.GaussianBlur(self.img_current, (kernel, kernel), 0)
        self.img_current[mask == 255] = blurred[mask == 255]
        self.image_panel.refresh()


    def apply_blur_rect(self, x: int, y: int, w: int, h: int):
        """Apply blur within a rectangular ROI."""
        if self.img_current is None or w == 0 or h == 0:
            return

        ratio_x, ratio_y = self._get_pixel_ratios()
        if ratio_x is None:
            return

        self.history.append(self.img_current.copy())

        real_h, real_w = self.img_current.shape[:2]
        rx = max(0, int(x * ratio_x))
        ry = max(0, int(y * ratio_y))
        rw = min(int(w * ratio_x), real_w - rx)
        rh = min(int(h * ratio_y), real_h - ry)

        if rw <= 0 or rh <= 0:
            return

        mask = np.zeros((real_h, real_w), dtype=np.uint8)
        cv2.rectangle(mask, (rx, ry), (rx + rw, ry + rh), 255, -1)
        self._apply_mask_blur(mask)


    def apply_blur_circle(self, cx: int, cy: int, radius: int):
        """Apply blur within a circular ROI."""
        if self.img_current is None or radius == 0:
            return

        ratio_x, ratio_y = self._get_pixel_ratios()
        if ratio_x is None:
            return

        self.history.append(self.img_current.copy())

        real_h, real_w  = self.img_current.shape[:2]
        real_cx     = int(cx * ratio_x)
        real_cy     = int(cy * ratio_y)
        real_radius = int(radius * (ratio_x + ratio_y) / 2)

        mask = np.zeros((real_h, real_w), dtype=np.uint8)
        cv2.circle(mask, (real_cx, real_cy), real_radius, 255, -1)
        self._apply_mask_blur(mask)


    def apply_blur_polygon(self, points: list):
        """Apply blur within a polygonal ROI."""
        if self.img_current is None or len(points) < 3:
            return

        ratio_x, ratio_y = self._get_pixel_ratios()
        if ratio_x is None:
            return

        self.history.append(self.img_current.copy())

        real_h, real_w = self.img_current.shape[:2]
        real_pts = np.array(
            [(int(x * ratio_x), int(y * ratio_y)) for x, y in points],
            dtype=np.int32
        )

        mask = np.zeros((real_h, real_w), dtype=np.uint8)
        cv2.fillPoly(mask, [real_pts], 255)
        self._apply_mask_blur(mask)


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
