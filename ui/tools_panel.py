from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QSlider, QStackedWidget, QFrame
)
from PySide6.QtGui import QIcon
from PySide6.QtCore import Qt, Signal

from ui.histogram_panel import HistogramPanel


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


def _make_slider_row(parent_layout, label: str, lo: int, hi: int, default: int):
    """Helper: add a labelled slider with a live value indicator.

    Returns (slider, value_label).
    """
    ly_header = QHBoxLayout()
    ly_header.setContentsMargins(0, 0, 0, 2)
    ly_header.addWidget(QLabel(label))
    ly_header.addStretch()
    lbl_val = QLabel(f'{default:+d}' if default != 0 else '0')
    lbl_val.setStyleSheet('color: #444; font-size: 10px; min-width: 30px;')
    ly_header.addWidget(lbl_val)
    parent_layout.addLayout(ly_header)

    slider = QSlider(Qt.Horizontal)
    slider.setRange(lo, hi)
    slider.setValue(default)
    slider.valueChanged.connect(
        lambda v, lbl=lbl_val: lbl.setText(f'{v:+d}' if v != 0 else '0')
    )
    parent_layout.addWidget(slider)
    return slider, lbl_val


class ToolsPanel(QWidget):
    """Left panel: checkable tool buttons at the top, a permanent ROI
    section (always visible between tools and options), and tool-specific
    options at the bottom."""

    # Tool-level signals
    grayscale_requested  = Signal()       # Grayscale button clicked
    adj_session_start    = Signal()       # any adjustment slider grabbed (sliderPressed)
    brightness_live      = Signal(int)    # brightness slider valueChanged
    contrast_live        = Signal(int)    # contrast slider valueChanged
    saturation_live      = Signal(int)    # saturation slider valueChanged
    blur_requested       = Signal()
    transform_requested  = Signal(str)   # 'flip_h' | 'flip_v' | 'rotate_cw' | 'rotate_ccw' | 'rotate_180'
    active_tool_changed  = Signal(str)   # 'adjustments' | 'blur' | 'transform' | 'none'

    # ROI signals
    roi_mode_changed = Signal(str)   # 'rectangle' | 'circle' | 'polygon' | 'brush' | 'none'

    def __init__(self, parent=None):
        super().__init__(parent)

        ly_main = QVBoxLayout(self)
        ly_main.setContentsMargins(4, 4, 4, 4)
        ly_main.setSpacing(6)

        # Tool buttons row
        ly_tools = QHBoxLayout()
        ly_main.addLayout(ly_tools)

        self.btn_adjustments = QPushButton()
        self.btn_adjustments.setIcon(QIcon('assets/grayscale.png'))
        self.btn_adjustments.setToolTip('Adjustments  (brightness, contrast, saturation, grayscale)')
        self.btn_adjustments.setCheckable(True)
        self.btn_adjustments.setStyleSheet(_BTN_STYLE)
        ly_tools.addWidget(self.btn_adjustments)

        self.btn_blur = QPushButton()
        self.btn_blur.setIcon(QIcon('assets/blur.png'))
        self.btn_blur.setToolTip('Blur')
        self.btn_blur.setCheckable(True)
        self.btn_blur.setStyleSheet(_BTN_STYLE)
        ly_tools.addWidget(self.btn_blur)

        self.btn_transform = QPushButton()
        self.btn_transform.setIcon(QIcon('assets/transform.png'))
        self.btn_transform.setToolTip('Transform  (flip / rotate)')
        self.btn_transform.setCheckable(True)
        self.btn_transform.setStyleSheet(_BTN_STYLE)
        ly_tools.addWidget(self.btn_transform)

        self.btn_histogram = QPushButton()
        self.btn_histogram.setIcon(QIcon('assets/histogram.png'))
        self.btn_histogram.setToolTip('Histogram  (levels per channel)')
        self.btn_histogram.setCheckable(True)
        self.btn_histogram.setStyleSheet(_BTN_STYLE)
        ly_tools.addWidget(self.btn_histogram)

        ly_tools.addStretch()

        #Permanent ROI / Selection section
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

        # Tool options (stacked widget)
        self.tool_options = QStackedWidget()
        ly_main.addWidget(self.tool_options)

        ly_main.addStretch()

        # Image info panel — pinned to the bottom of the tools column
        sep_info = QFrame()
        sep_info.setFrameShape(QFrame.HLine)
        sep_info.setFrameShadow(QFrame.Sunken)
        ly_main.addWidget(sep_info)

        _info_style = 'color: #555; font-size: 10px; font-family: monospace;'

        self.lbl_resolution = QLabel('No image')
        self.lbl_resolution.setStyleSheet(_info_style)
        ly_main.addWidget(self.lbl_resolution)

        self.lbl_viewport_tl = QLabel('')
        self.lbl_viewport_tl.setStyleSheet(_info_style)
        ly_main.addWidget(self.lbl_viewport_tl)

        self.lbl_viewport_br = QLabel('')
        self.lbl_viewport_br.setStyleSheet(_info_style)
        ly_main.addWidget(self.lbl_viewport_br)

        # Default (empty) page
        self._page_default = QWidget()
        ly_default = QVBoxLayout(self._page_default)
        ly_default.addWidget(QLabel('Choose tool'))
        self.tool_options.addWidget(self._page_default)

        #Adjustments page
        self._page_adjustments = QWidget()
        ly_adj = QVBoxLayout(self._page_adjustments)
        ly_adj.setSpacing(4)
        ly_adj.setContentsMargins(2, 4, 2, 4)

        # Brightness
        self.slider_brightness, _ = _make_slider_row(ly_adj, 'Brightness:', -100, 100, 0)

        ly_adj.addSpacing(6)

        # Contrast
        self.slider_contrast, _ = _make_slider_row(ly_adj, 'Contrast:', -100, 100, 0)

        ly_adj.addSpacing(6)

        # Saturation
        self.slider_saturation, _ = _make_slider_row(ly_adj, 'Saturation:', -100, 100, 0)

        ly_adj.addSpacing(6)

        # Separator before grayscale
        sep_gray = QFrame()
        sep_gray.setFrameShape(QFrame.HLine)
        sep_gray.setFrameShadow(QFrame.Sunken)
        ly_adj.addWidget(sep_gray)

        # Grayscale — one-click conversion, no slider needed
        self.btn_grayscale = QPushButton('Grayscale')
        ly_adj.addWidget(self.btn_grayscale)

        ly_adj.addStretch()
        self.tool_options.addWidget(self._page_adjustments)

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

        # Transform page
        self._page_transform = QWidget()
        ly_tr = QVBoxLayout(self._page_transform)
        ly_tr.setSpacing(6)
        ly_tr.setContentsMargins(2, 4, 2, 4)

        ly_tr.addWidget(QLabel('Flip:'))
        ly_flip = QHBoxLayout()
        self.btn_flip_h = QPushButton('↔  Horizontal')
        self.btn_flip_h.setToolTip('Mirror left ↔ right')
        self.btn_flip_v = QPushButton('↕  Vertical')
        self.btn_flip_v.setToolTip('Mirror top ↕ bottom')
        ly_flip.addWidget(self.btn_flip_h)
        ly_flip.addWidget(self.btn_flip_v)
        ly_tr.addLayout(ly_flip)

        ly_tr.addSpacing(4)
        ly_tr.addWidget(QLabel('Rotate:'))

        ly_rot1 = QHBoxLayout()
        self.btn_rotate_ccw = QPushButton('↺  90° CCW')
        self.btn_rotate_ccw.setToolTip('Rotate 90° counter-clockwise')
        self.btn_rotate_cw  = QPushButton('↻  90° CW')
        self.btn_rotate_cw.setToolTip('Rotate 90° clockwise')
        ly_rot1.addWidget(self.btn_rotate_ccw)
        ly_rot1.addWidget(self.btn_rotate_cw)
        ly_tr.addLayout(ly_rot1)

        self.btn_rotate_180 = QPushButton('⇄  180°')
        self.btn_rotate_180.setToolTip('Rotate 180°')
        ly_tr.addWidget(self.btn_rotate_180)

        ly_tr.addStretch()
        self.tool_options.addWidget(self._page_transform)

        # Histogram page — contains the full HistogramPanel widget
        self._page_histogram = QWidget()
        ly_hist = QVBoxLayout(self._page_histogram)
        ly_hist.setContentsMargins(0, 0, 0, 0)
        ly_hist.setSpacing(0)
        self.histogram_panel = HistogramPanel()
        ly_hist.addWidget(self.histogram_panel)
        self.tool_options.addWidget(self._page_histogram)

        # Signal connections
        self.btn_adjustments.clicked.connect(
            lambda: self._on_tool_clicked(self.btn_adjustments, 'adjustments'))
        self.btn_blur.clicked.connect(
            lambda: self._on_tool_clicked(self.btn_blur, 'blur'))
        self.btn_transform.clicked.connect(
            lambda: self._on_tool_clicked(self.btn_transform, 'transform'))
        self.btn_histogram.clicked.connect(
            lambda: self._on_tool_clicked(self.btn_histogram, 'histogram'))

        # Live adjustment sliders: sliderPressed starts a session, valueChanged streams the value
        for sl, sig in (
            (self.slider_brightness, self.brightness_live),
            (self.slider_contrast,   self.contrast_live),
            (self.slider_saturation, self.saturation_live),
        ):
            sl.sliderPressed.connect(self.adj_session_start)
            sl.valueChanged.connect(sig)
        self.btn_grayscale.clicked.connect(self.grayscale_requested)
        self.btn_apply_blur.clicked.connect(self.blur_requested)

        self.btn_flip_h.clicked.connect(lambda: self.transform_requested.emit('flip_h'))
        self.btn_flip_v.clicked.connect(lambda: self.transform_requested.emit('flip_v'))
        self.btn_rotate_cw.clicked.connect(lambda: self.transform_requested.emit('rotate_cw'))
        self.btn_rotate_ccw.clicked.connect(lambda: self.transform_requested.emit('rotate_ccw'))
        self.btn_rotate_180.clicked.connect(lambda: self.transform_requested.emit('rotate_180'))

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

        for btn in (self.btn_adjustments, self.btn_blur,
                    self.btn_transform, self.btn_histogram):
            if btn is not clicked_btn:
                btn.setChecked(False)

        if is_now_checked:
            if tool_name == 'adjustments':
                self.tool_options.setCurrentWidget(self._page_adjustments)
            elif tool_name == 'blur':
                self.tool_options.setCurrentWidget(self._page_blur)
            elif tool_name == 'transform':
                self.tool_options.setCurrentWidget(self._page_transform)
            elif tool_name == 'histogram':
                self.tool_options.setCurrentWidget(self._page_histogram)
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
        """Update the selection status label."""
        self.lbl_roi_status.setText(text)


    def get_brightness(self) -> int:
        """Return the current brightness adjustment value (-100 … +100)."""
        return self.slider_brightness.value()

    def get_contrast(self) -> int:
        """Return the current contrast adjustment value (-100 … +100)."""
        return self.slider_contrast.value()

    def get_saturation(self) -> int:
        """Return the current saturation adjustment value (-100 … +100)."""
        return self.slider_saturation.value()

    def get_blur_kernel(self) -> int:
        """Return current blur kernel size (always an odd number)."""
        return self.slider_blur.value() * 2 + 1

    def get_brush_size(self) -> int:
        """Return current brush radius in display pixels."""
        return self.slider_brush_size.value()


    def set_image_info(self, resolution, coords):
        """Update the image info panel at the bottom of the tools column.

        resolution  (width, height) tuple in pixels, or None when no image.
        coords      (x0, y0, x1, y1) image-pixel coordinates of the visible
                    viewport corners (top-left and bottom-right), or None.
        """
        if resolution is None:
            self.lbl_resolution.setText('No image')
            self.lbl_viewport_tl.setText('')
            self.lbl_viewport_br.setText('')
            return

        w, h = resolution
        self.lbl_resolution.setText(f'{w} x {h} px')

        if coords is not None:
            x0, y0, x1, y1 = coords
            self.lbl_viewport_tl.setText(f'TL  ({x0}, {y0})')
            self.lbl_viewport_br.setText(f'BR  ({x1}, {y1})')
        else:
            self.lbl_viewport_tl.setText('')
            self.lbl_viewport_br.setText('')


    def reset_adjustment_sliders(self):
        """Reset brightness, contrast and saturation sliders to 0.

        Called whenever a new selection is committed or the current selection
        is cleared, so each new region starts with neutral slider values.

        Programmatic setValue() does NOT fire sliderPressed, so no adjustment
        session is opened.  The valueChanged signal does fire, but the live
        handlers return immediately because _adj_base is None at that point.
        """
        for sl in (self.slider_brightness, self.slider_contrast, self.slider_saturation):
            sl.setValue(0)