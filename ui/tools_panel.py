from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QSlider, QStackedWidget, QFrame
)
from PySide6.QtGui import QIcon
from PySide6.QtCore import Qt, Signal


_BTN_STYLE = """
QPushButton {
    border: 1px solid #c0c0c0;
    border-radius: 4px;
    padding: 4px;
    background-color: transparent;
}
QPushButton:hover:!checked {
    background-color: #dbe9f9;
    border-color: #88b4e0;
}
QPushButton:checked {
    background-color: #b3d4f5;
    border: 2px solid #2878be;
}
QPushButton:checked:hover {
    background-color: #94c2ef;
}
"""


class ToolsPanel(QWidget):
    """Left panel: checkable tool buttons at the top, a permanent ROI
    section (always visible between tools and options), and tool-specific
    options at the bottom."""

    grayscale_requested = Signal()
    blur_requested      = Signal()
    active_tool_changed = Signal(str)   # 'grayscale' | 'blur' | 'none'
    roi_mode_changed    = Signal(str)   # 'rectangle' | 'circle' | 'polygon' | 'brush' | 'none'

    def __init__(self, parent=None):
        super().__init__(parent)

        ly_main = QVBoxLayout(self)
        ly_main.setContentsMargins(4, 4, 4, 4)
        ly_main.setSpacing(6)

        # ── Tool buttons row ──────────────────────────────────────────────────
        ly_tools = QHBoxLayout()
        ly_main.addLayout(ly_tools)

        self.btn_grayscale = QPushButton()
        self.btn_grayscale.setIcon(QIcon('assets/grayscale.png'))
        self.btn_grayscale.setToolTip('Grayscale')
        self.btn_grayscale.setCheckable(True)
        self.btn_grayscale.setStyleSheet(_BTN_STYLE)
        ly_tools.addWidget(self.btn_grayscale)

        self.btn_blur = QPushButton()
        self.btn_blur.setIcon(QIcon('assets/blur.png'))
        self.btn_blur.setToolTip('Blur')
        self.btn_blur.setCheckable(True)
        self.btn_blur.setStyleSheet(_BTN_STYLE)
        ly_tools.addWidget(self.btn_blur)

        ly_tools.addStretch()

        # ── Permanent ROI / Selection section ─────────────────────────────────
        sep_top = QFrame()
        sep_top.setFrameShape(QFrame.HLine)
        sep_top.setFrameShadow(QFrame.Sunken)
        ly_main.addWidget(sep_top)

        self.lbl_roi_status = QLabel('None')
        self.lbl_roi_status.setStyleSheet('color: #666; font-size: 10px;')
        ly_main.addWidget(self.lbl_roi_status)

        ly_roi = QHBoxLayout()
        ly_roi.setSpacing(4)
        ly_roi.setContentsMargins(0, 0, 0, 0)

        self.btn_roi_rect = QPushButton()
        self.btn_roi_rect.setIcon(QIcon('assets/ROI_rectangle.png'))
        self.btn_roi_rect.setToolTip('Rectangle selection')
        self.btn_roi_rect.setCheckable(True)
        self.btn_roi_rect.setStyleSheet(_BTN_STYLE)
        ly_roi.addWidget(self.btn_roi_rect)

        self.btn_roi_circle = QPushButton()
        self.btn_roi_circle.setIcon(QIcon('assets/ROI_circle.png'))
        self.btn_roi_circle.setToolTip('Circle selection')
        self.btn_roi_circle.setCheckable(True)
        self.btn_roi_circle.setStyleSheet(_BTN_STYLE)
        ly_roi.addWidget(self.btn_roi_circle)

        self.btn_roi_polygon = QPushButton()
        self.btn_roi_polygon.setIcon(QIcon('assets/ROI_polygon.png'))
        self.btn_roi_polygon.setToolTip('Polygon selection  (RMB to close,  Esc to cancel)')
        self.btn_roi_polygon.setCheckable(True)
        self.btn_roi_polygon.setStyleSheet(_BTN_STYLE)
        ly_roi.addWidget(self.btn_roi_polygon)

        self.btn_roi_brush = QPushButton()
        self.btn_roi_brush.setIcon(QIcon('assets/brush.png'))
        self.btn_roi_brush.setToolTip('Brush  (paints with the active tool — blur or grayscale)')
        self.btn_roi_brush.setCheckable(True)
        self.btn_roi_brush.setStyleSheet(_BTN_STYLE)
        ly_roi.addWidget(self.btn_roi_brush)

        ly_roi.addStretch()
        ly_main.addLayout(ly_roi)

        sep_bot = QFrame()
        sep_bot.setFrameShape(QFrame.HLine)
        sep_bot.setFrameShadow(QFrame.Sunken)
        ly_main.addWidget(sep_bot)

        # ── Tool options (stacked widget) ─────────────────────────────────────
        self.tool_options = QStackedWidget()
        ly_main.addWidget(self.tool_options)

        ly_main.addStretch()

        # Default (empty) page
        self._page_default = QWidget()
        ly_default = QVBoxLayout(self._page_default)
        ly_default.addWidget(QLabel('Choose tool'))
        self.tool_options.addWidget(self._page_default)

        # Grayscale page
        self._page_grayscale = QWidget()
        ly_grayscale = QVBoxLayout(self._page_grayscale)
        self.btn_apply_grayscale = QPushButton('Apply Grayscale')
        ly_grayscale.addWidget(self.btn_apply_grayscale)
        ly_grayscale.addStretch()
        self.tool_options.addWidget(self._page_grayscale)

        # Blur page
        self._page_blur = QWidget()
        ly_blur = QVBoxLayout(self._page_blur)
        ly_blur.setSpacing(6)

        ly_blur.addWidget(QLabel('Blur strength:'))
        self.slider_blur = QSlider(Qt.Horizontal)
        self.slider_blur.setRange(1, 50)
        self.slider_blur.setValue(10)
        ly_blur.addWidget(self.slider_blur)

        ly_blur.addWidget(QLabel('Brush size:'))
        self.slider_brush_size = QSlider(Qt.Horizontal)
        self.slider_brush_size.setRange(5, 100)
        self.slider_brush_size.setValue(20)
        ly_blur.addWidget(self.slider_brush_size)

        self.btn_apply_blur = QPushButton('Apply Blur')
        ly_blur.addWidget(self.btn_apply_blur)
        ly_blur.addStretch()
        self.tool_options.addWidget(self._page_blur)

        # ── Signal connections ────────────────────────────────────────────────
        self.btn_grayscale.clicked.connect(
            lambda: self._on_tool_clicked(self.btn_grayscale, 'grayscale'))
        self.btn_blur.clicked.connect(
            lambda: self._on_tool_clicked(self.btn_blur, 'blur'))

        self.btn_apply_grayscale.clicked.connect(self.grayscale_requested)
        self.btn_apply_blur.clicked.connect(self.blur_requested)

        self.btn_roi_rect.clicked.connect(
            lambda: self._on_roi_clicked(self.btn_roi_rect, 'rectangle'))
        self.btn_roi_circle.clicked.connect(
            lambda: self._on_roi_clicked(self.btn_roi_circle, 'circle'))
        self.btn_roi_polygon.clicked.connect(
            lambda: self._on_roi_clicked(self.btn_roi_polygon, 'polygon'))
        self.btn_roi_brush.clicked.connect(
            lambda: self._on_roi_clicked(self.btn_roi_brush, 'brush'))


    def _on_tool_clicked(self, clicked_btn: QPushButton, tool_name: str):
        """Handle a tool button click (checkable toggle with mutual exclusion).
        ROI section is independent and not affected by tool switching."""
        is_now_checked = clicked_btn.isChecked()

        for btn in (self.btn_grayscale, self.btn_blur):
            if btn is not clicked_btn:
                btn.setChecked(False)

        if is_now_checked:
            if tool_name == 'grayscale':
                self.tool_options.setCurrentWidget(self._page_grayscale)
            elif tool_name == 'blur':
                self.tool_options.setCurrentWidget(self._page_blur)
            self.active_tool_changed.emit(tool_name)
        else:
            self.tool_options.setCurrentWidget(self._page_default)
            self.active_tool_changed.emit('none')


    def _on_roi_clicked(self, clicked_btn: QPushButton, mode: str):
        """Handle a ROI/selection button click (checkable toggle with mutual exclusion)."""
        is_now_checked = clicked_btn.isChecked()

        for btn in (self.btn_roi_rect, self.btn_roi_circle, self.btn_roi_polygon, self.btn_roi_brush):
            if btn is not clicked_btn:
                btn.setChecked(False)

        self.roi_mode_changed.emit(mode if is_now_checked else 'none')


    def _deactivate_roi_buttons(self):
        """Uncheck all ROI/selection buttons and reset the draw mode."""
        for btn in (self.btn_roi_rect, self.btn_roi_circle, self.btn_roi_polygon, self.btn_roi_brush):
            btn.setChecked(False)
        self.roi_mode_changed.emit('none')


    def set_roi_status(self, text: str):
        """Update the selection status label shown next to 'Selection:'."""
        self.lbl_roi_status.setText(text)


    def get_blur_kernel(self):
        """Return current blur kernel size (always an odd number)."""
        return self.slider_blur.value() * 2 + 1


    def get_brush_size(self):
        """Return current brush radius in display pixels."""
        return self.slider_brush_size.value()