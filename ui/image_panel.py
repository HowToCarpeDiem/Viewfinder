import math

import cv2
from PySide6.QtWidgets import QScrollArea, QLabel
from PySide6.QtGui import QImage, QPixmap, QPainter, QPen, QColor
from PySide6.QtCore import Qt, Signal, QPoint


class InteractiveLabel(QLabel):
    """
    Label that supports multiple ROI drawing modes (LMB) and RMB panning.

    draw_mode controls the active drawing tool:
        None         – no drawing, only RMB panning
        'rectangle'  – drag to select a rectangle
        'circle'     – drag to select a circle (center → edge)
        'polygon'    – click to add vertices; double-click to close;  Esc to cancel
    """

    roi_rect_selected    = Signal(int, int, int, int)   # x, y, w, h
    roi_circle_selected  = Signal(int, int, int)         # cx, cy, radius
    roi_polygon_selected = Signal(object)                # list of (x, y) tuples

    pan_delta = Signal(int, int)   

    def __init__(self, parent=None):
        super().__init__(parent)

        self.draw_mode = None   # None | 'rectangle' | 'circle' | 'polygon'

        # Rectangle state
        self.x_start    = None
        self.y_start    = None
        self.x_end      = None
        self.y_end      = None
        self.is_drawing = False

        # Circle state
        self._circle_center = None
        self._circle_end    = None

        # Polygon state
        self._polygon_points = []  
        self._cursor_pos     = None

        # RMB panning state
        self._pan_last = QPoint()


    def set_draw_mode(self, mode):
        """Set the drawing mode and clear any in-progress shape."""
        self.draw_mode = mode
        self._clear_state()


    def _clear_state(self):
        self.x_start = self.y_start = self.x_end = self.y_end = None
        self.is_drawing = False
        self._circle_center = self._circle_end = None
        self._polygon_points.clear()
        self._cursor_pos = None
        self.update()


    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            self._pan_last = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            return

        if event.button() != Qt.LeftButton or self.draw_mode is None:
            return

        if self.draw_mode == 'rectangle':
            self.is_drawing = True
            self.x_start = event.pos().x()
            self.y_start = event.pos().y()
            self.x_end = self.y_end = None

        elif self.draw_mode == 'circle':
            self.is_drawing    = True
            self._circle_center = event.pos()
            self._circle_end    = event.pos()

        elif self.draw_mode == 'polygon':
            self._polygon_points.append(event.pos())
            self._cursor_pos = event.pos()
            self.update()


    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.RightButton:
            delta = event.pos() - self._pan_last
            self._pan_last = event.pos()
            self.pan_delta.emit(delta.x(), delta.y())
            return

        if self.draw_mode == 'rectangle' and self.is_drawing:
            self.x_end = event.pos().x()
            self.y_end = event.pos().y()
            self.update()

        elif self.draw_mode == 'circle' and self.is_drawing:
            self._circle_end = event.pos()
            self.update()

        elif self.draw_mode == 'polygon' and self._polygon_points:
            self._cursor_pos = event.pos()
            self.update()


    def mouseReleaseEvent(self, event):
        if event.button() == Qt.RightButton:
            self.setCursor(Qt.ArrowCursor)
            return

        if event.button() != Qt.LeftButton:
            return

        if self.draw_mode == 'rectangle' and self.is_drawing:
            self.x_end = event.pos().x()
            self.y_end = event.pos().y()
            self.is_drawing = False

            x_rect = min(self.x_start, self.x_end)
            y_rect = min(self.y_start, self.y_end)
            w = abs(self.x_start - self.x_end)
            h = abs(self.y_start - self.y_end)
            self.roi_rect_selected.emit(x_rect, y_rect, w, h)
            self.update()

        elif self.draw_mode == 'circle' and self.is_drawing:
            self._circle_end = event.pos()
            self.is_drawing  = False

            cx     = self._circle_center.x()
            cy     = self._circle_center.y()
            radius = int(math.hypot(self._circle_end.x() - cx,
                                    self._circle_end.y() - cy))
            if radius > 0:
                self.roi_circle_selected.emit(cx, cy, radius)
            self.update()


    def mouseDoubleClickEvent(self, event):
        if event.button() != Qt.LeftButton or self.draw_mode != 'polygon':
            return

        if self._polygon_points:
            self._polygon_points.pop()

        if len(self._polygon_points) >= 3:
            points = [(p.x(), p.y()) for p in self._polygon_points]
            self.roi_polygon_selected.emit(points)

        self._polygon_points.clear()
        self._cursor_pos = None
        self.update()


    def keyPressEvent(self, event):
        """Esc cancels an in-progress polygon."""
        if event.key() == Qt.Key_Escape and self.draw_mode == 'polygon':
            self._polygon_points.clear()
            self._cursor_pos = None
            self.update()
        else:
            super().keyPressEvent(event)


    def paintEvent(self, event):
        super().paintEvent(event)
        if self.draw_mode is None:
            return

        painter = QPainter(self)

        if self.draw_mode == 'rectangle':
            self._paint_rectangle(painter)
        elif self.draw_mode == 'circle':
            self._paint_circle(painter)
        elif self.draw_mode == 'polygon':
            self._paint_polygon(painter)


    def _paint_rectangle(self, painter: QPainter):
        if self.x_start is None or self.x_end is None:
            return
        painter.setPen(QPen(Qt.red, 2, Qt.SolidLine))
        x_rect = min(self.x_start, self.x_end)
        y_rect = min(self.y_start, self.y_end)
        w = abs(self.x_start - self.x_end)
        h = abs(self.y_start - self.y_end)
        painter.drawRect(x_rect, y_rect, w, h)


    def _paint_circle(self, painter: QPainter):
        if self._circle_center is None or self._circle_end is None:
            return
        cx     = self._circle_center.x()
        cy     = self._circle_center.y()
        radius = int(math.hypot(self._circle_end.x() - cx,
                                self._circle_end.y() - cy))
        painter.setPen(QPen(Qt.red, 2, Qt.SolidLine))
        # drawEllipse(QPoint center, int rx, int ry)
        painter.drawEllipse(self._circle_center, radius, radius)


    def _paint_polygon(self, painter: QPainter):
        if not self._polygon_points:
            return

        # Completed edges
        painter.setPen(QPen(Qt.red, 2, Qt.SolidLine))
        for i in range(len(self._polygon_points) - 1):
            painter.drawLine(self._polygon_points[i], self._polygon_points[i + 1])

        # Preview edge from last vertex to current cursor position
        if self._cursor_pos is not None:
            painter.setPen(QPen(QColor(255, 80, 80), 1, Qt.DashLine))
            painter.drawLine(self._polygon_points[-1], self._cursor_pos)

        # Vertex dots
        painter.setPen(QPen(Qt.red, 2, Qt.SolidLine))
        for pt in self._polygon_points:
            painter.drawEllipse(pt.x() - 3, pt.y() - 3, 6, 6)


class ImagePanel(QScrollArea):
    """
    Scrollable image display panel.

    Zoom is controlled with Ctrl+Mouse Wheel.
    scale_factor=1.0  → image fits inside the panel (keeping aspect ratio).
    scale_factor>1.0  → image is larger than the panel; scroll bars appear.
    scale_factor<1.0  → image is smaller than the panel.
    RMB drag pans the viewport.
    """

    ZOOM_STEP = 0.1
    ZOOM_MIN  = 0.1
    ZOOM_MAX  = 5.0

    def __init__(self, parent=None):
        super().__init__(parent)

        self.scale_factor = 1.0
        self._img_bgr = None

        self.lb_image = InteractiveLabel()
        self.lb_image.setAlignment(Qt.AlignCenter)

        self.setWidget(self.lb_image)
        self.setAlignment(Qt.AlignCenter)
        self.setWidgetResizable(False)

        self.lb_image.pan_delta.connect(self._on_pan)


    def set_image(self, img_bgr):
        """Display a new image and reset zoom to 1.0."""
        self._img_bgr = img_bgr
        self.scale_factor = 1.0
        self._render()


    def update_image(self, img_bgr):
        """Replace the displayed image without changing the current zoom level."""
        self._img_bgr = img_bgr
        self._render()


    def refresh(self):
        """Re-render the current image (useful after an in-place edit)."""
        self._render()


    def set_draw_mode(self, mode):
        """Set the ROI drawing mode on the image label (None to disable all drawing)."""
        self.lb_image.set_draw_mode(mode)


    def wheelEvent(self, event):
        if event.modifiers() == Qt.ControlModifier:
            if event.angleDelta().y() > 0:
                self.scale_factor = min(self.scale_factor + self.ZOOM_STEP, self.ZOOM_MAX)
            else:
                self.scale_factor = max(self.scale_factor - self.ZOOM_STEP, self.ZOOM_MIN)
            self._render()
        else:
            super().wheelEvent(event)


    def resizeEvent(self, event):
        """Re-render on resize so the image always fills the available space at scale=1.0."""
        super().resizeEvent(event)
        self._render()


    def _on_pan(self, dx: int, dy: int):
        """Scroll the viewport in response to a RMB drag on the image label."""
        self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - dx)
        self.verticalScrollBar().setValue(self.verticalScrollBar().value() - dy)


    def _render(self):
        if self._img_bgr is None:
            return

        img_rgb = cv2.cvtColor(self._img_bgr, cv2.COLOR_BGR2RGB)
        h, w, ch = img_rgb.shape
        q_img = QImage(img_rgb.data, w, h, ch * w, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(q_img)

        vp_w = max(1, self.viewport().width())
        vp_h = max(1, self.viewport().height())
        target_w = int(vp_w * self.scale_factor)
        target_h = int(vp_h * self.scale_factor)

        scaled = pixmap.scaled(target_w, target_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.lb_image.setPixmap(scaled)
        self.lb_image.adjustSize()