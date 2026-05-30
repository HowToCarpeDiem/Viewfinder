import math

import cv2
import numpy as np
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
    brush_stroke         = Signal(int, int, bool)        # x, y, is_first_point

    pan_delta = Signal(int, int)   

    def __init__(self, parent=None):
        super().__init__(parent)

        self.draw_mode = None   # None | 'rectangle' | 'circle' | 'polygon' | 'brush'

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

        # Brush state
        self._brush_active    = False   
        self._brush_pos       = None    
        self._brush_radius    = 20      
        self._brush_last_emit = None    

        # Committed (persisted) ROI — normalised to [0, 1] of the pixmap size
        # so the outline stays correct after zoom changes.
        self._committed_roi_norm = None

        # RMB panning state
        self._pan_last         = QPoint()
        self._pan_press_global = QPoint()  # global pos at the moment of RMB press
        self._pan_did_drag     = False     # True once the pointer moves beyond the click threshold


    def set_draw_mode(self, mode):
        """Set the drawing mode and clear any in-progress shape."""
        self.draw_mode = mode
        self._clear_state()
        if mode == 'brush':
            self.setCursor(Qt.CrossCursor)
            self.setMouseTracking(True)
        else:
            self.setCursor(Qt.ArrowCursor)
            self.setMouseTracking(False)


    def _clear_state(self):
        self.x_start = self.y_start = self.x_end = self.y_end = None
        self.is_drawing = False
        self._circle_center = self._circle_end = None
        self._polygon_points.clear()
        self._cursor_pos = None
        self._brush_active    = False
        self._brush_pos       = None
        self._brush_last_emit = None
        self.update()


    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            g = event.globalPosition().toPoint()
            self._pan_press_global = g
            self._pan_last         = g
            self._pan_did_drag     = False
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

        elif self.draw_mode == 'brush':
            self._brush_active    = True
            self._brush_pos       = event.pos()
            self._brush_last_emit = event.pos()
            self.brush_stroke.emit(event.pos().x(), event.pos().y(), True)
            self.update()


    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.RightButton:
            current = event.globalPosition().toPoint()
            if not self._pan_did_drag:
                # Check whether the pointer has moved far enough to count as a drag
                diff = current - self._pan_press_global
                if abs(diff.x()) > 5 or abs(diff.y()) > 5:
                    self._pan_did_drag = True
                    self._pan_last = current   # anchor to avoid a jump on first pan delta
                    self.setCursor(Qt.ClosedHandCursor)
            if self._pan_did_drag:
                # Use global coords — local coords shift when the scroll area scrolls,
                # which would corrupt the delta and cause visible jitter.
                delta = current - self._pan_last
                self._pan_last = current
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

        elif self.draw_mode == 'brush':
            self._brush_pos = event.pos()
            if self._brush_active:
                # Emit only when the cursor moved far enough — prevents flooding
                # the blur pipeline with near-duplicate points during fast drags.
                threshold = max(2, self._brush_radius * 0.3)
                if self._brush_last_emit is not None:
                    dx = event.pos().x() - self._brush_last_emit.x()
                    dy = event.pos().y() - self._brush_last_emit.y()
                    moved = math.hypot(dx, dy)
                else:
                    moved = threshold  
                if moved >= threshold:
                    self._brush_last_emit = event.pos()
                    self.brush_stroke.emit(event.pos().x(), event.pos().y(), False)
            self.update()


    def mouseReleaseEvent(self, event):
        if event.button() == Qt.RightButton:
            self.setCursor(Qt.CrossCursor if self.draw_mode == 'brush' else Qt.ArrowCursor)
            if not self._pan_did_drag and self.draw_mode == 'polygon' and self._polygon_points:
                # RMB click (no drag) while drawing a polygon — close it
                if len(self._polygon_points) >= 3:
                    points = [(p.x(), p.y()) for p in self._polygon_points]
                    self.roi_polygon_selected.emit(points)
                self._polygon_points.clear()
                self._cursor_pos = None
                self.update()
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

        elif self.draw_mode == 'brush' and self._brush_active:
            self._brush_active = False
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

        painter = QPainter(self)

        # Always draw the committed selection outline (visible regardless of draw mode)
        self._paint_committed_roi(painter)

        # Draw the in-progress shape (only when a draw mode is active)
        if self.draw_mode == 'rectangle':
            self._paint_rectangle(painter)
        elif self.draw_mode == 'circle':
            self._paint_circle(painter)
        elif self.draw_mode == 'polygon':
            self._paint_polygon(painter)
        elif self.draw_mode == 'brush':
            self._paint_brush_cursor(painter)


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


    def _paint_brush_cursor(self, painter: QPainter):
        """Draw a semi-transparent circle showing the current brush size."""
        if self._brush_pos is None:
            return
        r = self._brush_radius
        # Outer ring — always visible regardless of background colour
        painter.setPen(QPen(QColor(0, 0, 0, 180), 1, Qt.SolidLine))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(self._brush_pos.x() - r, self._brush_pos.y() - r, r * 2, r * 2)
        # Inner ring — white inner highlight for contrast
        painter.setPen(QPen(QColor(255, 255, 255, 140), 1, Qt.DashLine))
        painter.drawEllipse(self._brush_pos.x() - r + 1, self._brush_pos.y() - r + 1,
                            r * 2 - 2, r * 2 - 2)


    def set_committed_roi(self, roi_dict: dict):
        """Store the committed ROI shape for persistent on-screen visualisation.

        Coordinates in roi_dict are in display pixels at the time of the call;
        they are immediately normalised to [0, 1] of the current pixmap size so
        that the outline stays in the correct position after zoom changes.

        Expected keys by type:
            rectangle – x, y, w, h
            circle    – cx, cy, r
            polygon   – pts (list of (x, y) tuples)
            all       – no extra keys (draws border around the full pixmap)
        """
        pm = self.pixmap()
        if pm is None or pm.width() == 0 or pm.height() == 0:
            self._committed_roi_norm = None
            return

        pw, ph  = pm.width(), pm.height()
        t       = roi_dict['type']
        norm    = {'type': t}

        if t == 'rectangle':
            norm.update(
                x=roi_dict['x'] / pw,  y=roi_dict['y'] / ph,
                w=roi_dict['w'] / pw,  h=roi_dict['h'] / ph,
            )
        elif t == 'circle':
            avg = (pw + ph) / 2
            norm.update(
                cx=roi_dict['cx'] / pw,
                cy=roi_dict['cy'] / ph,
                r =roi_dict['r']  / avg,
            )
        elif t == 'polygon':
            norm.update(pts=[(p[0] / pw, p[1] / ph) for p in roi_dict['pts']])
        # 'all' type has no extra keys

        self._committed_roi_norm = norm
        self.update()


    def clear_roi_display(self):
        """Remove the committed selection overlay from the display."""
        self._committed_roi_norm = None
        self.update()


    def invert_roi_display(self):
        """Toggle the 'inverted' flag on the committed ROI.

        When inverted, _paint_committed_roi draws both the shape outline AND
        the full-image border, visually conveying 'everything outside the
        shape is selected'.  Calling this a second time restores the normal
        (non-inverted) outline.
        Has no effect if no committed ROI is currently displayed.
        """
        if self._committed_roi_norm is not None:
            was = self._committed_roi_norm.get('inverted', False)
            self._committed_roi_norm['inverted'] = not was
            self.update()


    def _paint_committed_roi(self, painter: QPainter):
        """Draw the persisted selection outline using a marching-ants style
        (two overlapping dashed pens: black outer + yellow inner).

        When the selection is inverted the image border is drawn in addition
        to the shape outline so the user can see both boundaries of the
        selected region (everything outside the shape).
        """
        if self._committed_roi_norm is None:
            return

        pm = self.pixmap()
        if pm is None or pm.width() == 0 or pm.height() == 0:
            return

        pw, ph      = pm.width(), pm.height()
        norm        = self._committed_roi_norm
        t           = norm['type']
        is_inverted = norm.get('inverted', False)

        painter.setBrush(Qt.NoBrush)

        # Draw twice: black outer dash then yellow inner dash (offset by 4 units)
        for color, offset in (
            (QColor(0,   0,   0, 200), 0),
            (QColor(255, 210, 0, 230), 4),
        ):
            pen = QPen(color, 1, Qt.DashLine)
            pen.setDashOffset(offset)
            painter.setPen(pen)

            # Inverted: also draw the full-image border so both boundaries
            # of the selected region are visible.
            if is_inverted and t != 'all':
                painter.drawRect(0, 0, pw - 1, ph - 1)

            if t == 'rectangle':
                x = int(norm['x'] * pw)
                y = int(norm['y'] * ph)
                w = int(norm['w'] * pw)
                h = int(norm['h'] * ph)
                painter.drawRect(x, y, w, h)

            elif t == 'circle':
                avg = (pw + ph) / 2
                cx  = int(norm['cx'] * pw)
                cy  = int(norm['cy'] * ph)
                r   = int(norm['r']  * avg)
                painter.drawEllipse(QPoint(cx, cy), r, r)

            elif t == 'polygon':
                pts = norm['pts']
                n   = len(pts)
                for i in range(n):
                    x1 = int(pts[i][0]           * pw)
                    y1 = int(pts[i][1]           * ph)
                    x2 = int(pts[(i + 1) % n][0] * pw)
                    y2 = int(pts[(i + 1) % n][1] * ph)
                    painter.drawLine(x1, y1, x2, y2)

            elif t == 'all':
                # 'all' inverted = nothing selected; draw border anyway for
                # visual consistency (mirrors the no-invert case).
                painter.drawRect(0, 0, pw - 1, ph - 1)


class ImagePanel(QScrollArea):
    """
    Scrollable image display panel.

    Zoom is controlled with Ctrl+Mouse Wheel.
    scale_factor=1.0  → image fits inside the panel (keeping aspect ratio).
    scale_factor>1.0  → image is larger than the panel; scroll bars appear.
    scale_factor<1.0  → image is smaller than the panel.
    RMB drag pans the viewport.
    """

    ZOOM_STEP = 0.2
    ZOOM_MIN  = 0.1
    ZOOM_MAX  = 5.0

    # Emitted every time the display is refreshed (zoom, resize, new image).
    # Connect to this to keep external info panels in sync.
    render_done = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.scale_factor = 1.0
        self._img_bgr      = None
        self._pixmap_cache = None   # QPixmap at native image resolution; None = needs rebuild

        self.lb_image = InteractiveLabel()
        self.lb_image.setAlignment(Qt.AlignCenter)

        self.setWidget(self.lb_image)
        self.setAlignment(Qt.AlignCenter)
        self.setWidgetResizable(False)

        self.lb_image.pan_delta.connect(self._on_pan)


    def set_image(self, img):
        """Display a new image (BGR or BGRA) and reset zoom to 1.0."""
        self._img_bgr      = img
        self._pixmap_cache = None   # image changed — rebuild display cache
        self.scale_factor  = 1.0
        self._render()


    def update_image(self, img):
        """Replace the displayed image (BGR or BGRA) without changing the current zoom level."""
        self._img_bgr      = img
        self._pixmap_cache = None   # image changed — rebuild display cache
        self._render()


    def refresh(self):
        """Re-render the current image after an in-place edit (img_current modified externally)."""
        self._pixmap_cache = None   # content changed in-place — rebuild display cache
        self._render()


    def set_draw_mode(self, mode):
        """Set the ROI drawing mode on the image label (None to disable all drawing)."""
        self.lb_image.set_draw_mode(mode)


    def wheelEvent(self, event):
        if event.modifiers() != Qt.ControlModifier:
            super().wheelEvent(event)
            return

        # ── Zoom-to-cursor ────────────────────────────────────────────────────
        # 1. Record where in the pixmap the cursor currently points.
        pm_before = self.lb_image.pixmap()
        cursor_vp = event.position().toPoint()   # cursor in viewport coords

        if pm_before is not None and pm_before.width() > 0:
            # Position of lb_image's top-left corner inside the viewport.
            # When the pixmap fits the viewport it is centred (Qt.AlignCenter);
            # when it overflows the scrollbars shift it.
            lb_w = self.lb_image.width()
            lb_h = self.lb_image.height()
            vp_w = self.viewport().width()
            vp_h = self.viewport().height()

            lb_x_in_vp = (vp_w - lb_w) // 2 if lb_w <= vp_w else -self.horizontalScrollBar().value()
            lb_y_in_vp = (vp_h - lb_h) // 2 if lb_h <= vp_h else -self.verticalScrollBar().value()

            # Fractional position of cursor within the pixmap (clamped to [0,1])
            frac_x = (cursor_vp.x() - lb_x_in_vp) / pm_before.width()
            frac_y = (cursor_vp.y() - lb_y_in_vp) / pm_before.height()
        else:
            frac_x = frac_y = 0.5   # no image yet — zoom towards centre

        # 2. Apply the new scale.
        if event.angleDelta().y() > 0:
            self.scale_factor = min(self.scale_factor + self.ZOOM_STEP, self.ZOOM_MAX)
        else:
            self.scale_factor = max(self.scale_factor - self.ZOOM_STEP, self.ZOOM_MIN)

        self._render()   # lb_image now has its new size

        # 3. Adjust scroll bars so the same image point stays under the cursor.
        pm_after = self.lb_image.pixmap()
        if pm_after is None or pm_after.width() == 0:
            return

        # Desired position of the anchor point in the new pixmap (px coords)
        target_x = frac_x * pm_after.width()
        target_y = frac_y * pm_after.height()

        # scroll = anchor_in_lb - cursor_in_viewport
        # Qt clamps setValue() to [minimum, maximum] automatically.
        self.horizontalScrollBar().setValue(int(target_x - cursor_vp.x()))
        self.verticalScrollBar().setValue(int(target_y - cursor_vp.y()))


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

        # Rebuild the display pixmap only when the image content has changed.
        # This avoids re-running _composite_on_checker (expensive numpy float
        # ops over the whole image) on every zoom or resize event.
        if self._pixmap_cache is None:
            img = self._img_bgr
            if img.ndim == 3 and img.shape[2] == 4:
                # BGRA — composite over a checkerboard so transparency is visible
                rgb = self._composite_on_checker(img)
            else:
                rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

            h, w = rgb.shape[:2]
            # fromImage copies the pixel data, so the numpy array can be
            # garbage-collected immediately after this line.
            self._pixmap_cache = QPixmap.fromImage(
                QImage(rgb.data, w, h, w * 3, QImage.Format_RGB888)
            )

        # Qt scales the cached QPixmap — this is a lightweight GPU-backed
        # operation and is safe to call on every zoom / resize event.
        vp_w = max(1, self.viewport().width())
        vp_h = max(1, self.viewport().height())
        target_w = int(vp_w * self.scale_factor)
        target_h = int(vp_h * self.scale_factor)

        scaled = self._pixmap_cache.scaled(
            target_w, target_h, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.lb_image.setPixmap(scaled)
        self.lb_image.adjustSize()
        self.render_done.emit()


    def get_viewport_image_coords(self):
        """Return (x0, y0, x1, y1): the image-pixel coordinates of the
        top-left and bottom-right corners of the currently visible viewport.

        Returns None when no image is loaded.

        The calculation accounts for centering (when the pixmap is smaller
        than the viewport Qt centres it and the scroll bars are at 0).
        """
        pm = self.lb_image.pixmap()
        if pm is None or self._img_bgr is None:
            return None

        pm_w, pm_h = pm.width(), pm.height()
        if pm_w == 0 or pm_h == 0:
            return None

        vp_w = self.viewport().width()
        vp_h = self.viewport().height()
        h_scroll = self.horizontalScrollBar().value()
        v_scroll = self.verticalScrollBar().value()

        # When the pixmap fits inside the viewport it is centred;
        # the whole pixmap is visible and scroll values are meaningless.
        if pm_w <= vp_w:
            x0_px, x1_px = 0, pm_w
        else:
            x0_px = h_scroll
            x1_px = min(h_scroll + vp_w, pm_w)

        if pm_h <= vp_h:
            y0_px, y1_px = 0, pm_h
        else:
            y0_px = v_scroll
            y1_px = min(v_scroll + vp_h, pm_h)

        img_h, img_w = self._img_bgr.shape[:2]
        rx = img_w / pm_w
        ry = img_h / pm_h

        return (
            int(x0_px * rx), int(y0_px * ry),
            int(x1_px * rx), int(y1_px * ry),
        )


    @staticmethod
    def _composite_on_checker(img_bgra: np.ndarray) -> np.ndarray:
        """Alpha-composite a BGRA image over an 8×8 grey/white checkerboard.

        Returns an RGB uint8 array suitable for display (no alpha channel).
        """
        h, w = img_bgra.shape[:2]
        tile = 8  # checker tile size in pixels

        # Vectorised checkerboard: XOR of tile-row and tile-col parity
        rows = np.arange(h, dtype=np.uint8) // tile
        cols = np.arange(w, dtype=np.uint8) // tile
        light = ((rows[:, np.newaxis] ^ cols[np.newaxis, :]) & 1).astype(np.uint8)
        checker_grey = (light * 51 + 204).astype(np.uint8)   # 204 or 255
        checker = np.stack([checker_grey] * 3, axis=-1)

        # Separate channels and blend: out = fg * a + bg * (1 - a)
        bgr    = img_bgra[:, :, :3].astype(np.float32)
        alpha  = (img_bgra[:, :, 3] / 255.0)[:, :, np.newaxis]
        rgb_fg = bgr[:, :, ::-1]                              # BGR → RGB
        blended = rgb_fg * alpha + checker.astype(np.float32) * (1.0 - alpha)
        return np.clip(blended, 0, 255).astype(np.uint8)
