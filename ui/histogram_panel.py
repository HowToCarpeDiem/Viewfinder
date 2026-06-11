import cv2
import numpy as np
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QSlider, QFrame, QSizePolicy
)
from PySide6.QtGui import QPainter, QColor, QPen, QBrush
from PySide6.QtCore import Qt, Signal, QRect


# Channel colours for the histogram curves
_CH_COLORS = {
    'r': QColor(220,  55,  55, 165),
    'g': QColor( 40, 180,  40, 165),
    'b': QColor( 50, 110, 220, 165),
    'l': QColor(200, 200, 200, 190),
}

# Shared button style
_BTN_STYLE = """
QPushButton {
    border: 1px solid #c0c0c0;
    border-radius: 4px;
    padding: 4px 8px;
    background-color: transparent;
    font-size: 11px;
}
QPushButton:hover { background-color: #dbe9f9; border-color: #88b4e0; }
QPushButton:pressed { background-color: #b3d4f5; }
"""


class HistogramDisplay(QWidget):
    """Draws R / G / B / Luminance histogram curves on a dark background.

    Call update_data({'r': arr, 'g': arr, 'b': arr, 'l': arr}) to refresh.
    Each array is a 256-element numpy array of raw pixel counts.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hists = {}
        self._show  = {'r', 'g', 'b', 'l'}
        self.setMinimumHeight(110)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def update_data(self, hist_dict: dict):
        """Accept raw-count arrays and normalise them to [0, 1] for drawing."""
        self._hists = {}
        for ch, arr in hist_dict.items():
            f    = arr.astype(np.float32)
            peak = f.max()
            self._hists[ch] = f / peak if peak > 0 else f
        self.update()

    def set_channel_visible(self, ch: str, visible: bool):
        if visible: self._show.add(ch)
        else:       self._show.discard(ch)
        self.update()

    def clear(self):
        self._hists = {}
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        w, h = self.width(), self.height()

        p.fillRect(0, 0, w, h, QColor(26, 26, 26))

        # Grid lines at 25 / 50 / 75 %
        p.setPen(QPen(QColor(50, 50, 50), 1, Qt.DotLine))
        for frac in (0.25, 0.50, 0.75):
            p.drawLine(0, int(h * (1 - frac)), w, int(h * (1 - frac)))
        p.drawLine(w // 2, 0, w // 2, h)

        if not self._hists:
            p.setPen(QColor(88, 88, 88))
            p.drawText(QRect(0, 0, w, h), Qt.AlignCenter, 'No image')
            return

        bw = w / 256.0
        for ch in ('l', 'b', 'g', 'r'):    # draw order: luma behind, R on top
            if ch not in self._show or ch not in self._hists:
                continue
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(_CH_COLORS[ch]))
            for i, val in enumerate(self._hists[ch]):
                bh = int(val * h)
                if bh < 1:
                    continue
                p.drawRect(int(i * bw), h - bh, max(1, int(bw)), bh)

        p.setPen(QPen(QColor(60, 60, 60), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRect(0, 0, w - 1, h - 1)


class HistogramPanel(QWidget):
    """Histogram display + per-channel Levels sliders + Reset.

    Signals (connected by MainWindow)
    -----------------------------------
    levels_preview(channel, black, gamma, white)
        channel: 'r' | 'g' | 'b' | 'all'
        Emitted on every slider move — host applies a live LUT without
        pushing a history entry.

    levels_commit(channel, black, gamma, white)
        Emitted when the user releases the slider — host pushes one undo
        entry and commits the result.

    levels_reset()
        Emitted when Reset is clicked — host reverts to the pre-session
        snapshot (_levels_pre) and resets slider positions.
    """

    levels_preview = Signal(str, int, float, int)   # channel, black, gamma, white
    levels_commit  = Signal(str, int, float, int)
    levels_reset   = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        ly = QVBoxLayout(self)
        ly.setContentsMargins(4, 4, 4, 4)
        ly.setSpacing(5)

        self.display = HistogramDisplay()
        ly.addWidget(self.display)

        # Channel toggle buttons
        ly_ch = QHBoxLayout()
        ly_ch.setSpacing(3)
        for ch, label, col in (
            ('r', 'R', '#dc3c3c'),
            ('g', 'G', '#28b428'),
            ('b', 'B', '#3264dc'),
            ('l', 'L', '#aaaaaa'),
        ):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(True)
            btn.setFixedSize(26, 20)
            btn.setStyleSheet(f"""
                QPushButton {{
                    border:1px solid #888; border-radius:3px;
                    font-size:10px; font-weight:bold;
                    color:{col}; background:transparent; padding:0;
                }}
                QPushButton:checked {{ background:{col}44; border-color:{col}; }}
            """)
            btn.clicked.connect(
                lambda checked, c=ch: self.display.set_channel_visible(c, checked)
            )
            ly_ch.addWidget(btn)
        ly_ch.addStretch()
        ly.addLayout(ly_ch)

        sep1 = QFrame(); sep1.setFrameShape(QFrame.HLine); sep1.setFrameShadow(QFrame.Sunken)
        ly.addWidget(sep1)


        self._sliders = {}  

        for ch, label, col in (
            ('all', 'All channels', '#cccccc'),
            ('r',   'Red',          '#dc3c3c'),
            ('g',   'Green',        '#28b428'),
            ('b',   'Blue',         '#3264dc'),
        ):
            grp = QWidget()
            g_ly = QVBoxLayout(grp)
            g_ly.setContentsMargins(0, 0, 0, 0)
            g_ly.setSpacing(2)

            # Channel label
            lbl_ch = QLabel(label)
            lbl_ch.setStyleSheet(f'font-size:10px; font-weight:bold; color:{col};')
            g_ly.addWidget(lbl_ch)

            sliders = {}
            for param, lo, hi, default, param_label in (
                ('black', 0,   254,  0,   'Black:'),
                ('gamma', 10,  1000, 100, 'Gamma:'),
                ('white', 1,   255,  255, 'White:'),
            ):
                row = QHBoxLayout()
                row.setSpacing(4)
                lbl = QLabel(param_label)
                lbl.setStyleSheet('font-size:9px; color:#888; min-width:34px;')
                lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                row.addWidget(lbl)

                sl = QSlider(Qt.Horizontal)
                sl.setRange(lo, hi)
                sl.setValue(default)
                row.addWidget(sl)

                lbl_val = QLabel(self._fmt_val(param, default))
                lbl_val.setStyleSheet('font-size:9px; color:#555; min-width:30px; font-family:monospace;')
                lbl_val.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                row.addWidget(lbl_val)

                g_ly.addLayout(row)
                sliders[param] = sl
                sl.valueChanged.connect(
                    lambda v, p=param, lv=lbl_val: lv.setText(self._fmt_val(p, v))
                )
                sl.sliderMoved.connect(
                    lambda _, c=ch: self._emit(c, 'preview')
                )
                sl.sliderReleased.connect(
                    lambda c=ch: self._emit(c, 'commit')
                )

            self._sliders[ch] = sliders
            ly.addWidget(grp)

        sep2 = QFrame(); sep2.setFrameShape(QFrame.HLine); sep2.setFrameShadow(QFrame.Sunken)
        ly.addWidget(sep2)

        # Reset button
        self.btn_reset = QPushButton('Reset')
        self.btn_reset.setToolTip(
            'Revert image to the state before the current Histogram session\n'
            'and reset all sliders to default.'
        )
        self.btn_reset.setStyleSheet(_BTN_STYLE)
        self.btn_reset.clicked.connect(self._on_reset)
        ly.addWidget(self.btn_reset)
        ly.addStretch()


    def update_histogram(self, img_bgr: np.ndarray, mask: np.ndarray | None = None):
        """Recompute and display the histogram.  mask is optional (uint8 0/255)."""
        if img_bgr is None:
            self.display.clear()
            return
        bgr  = img_bgr[:, :, :3]
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        kw   = dict(images=[bgr], mask=mask, histSize=[256], ranges=[0, 256])
        self.display.update_data({
            'b': cv2.calcHist(channels=[0], **kw).flatten(),
            'g': cv2.calcHist(channels=[1], **kw).flatten(),
            'r': cv2.calcHist(channels=[2], **kw).flatten(),
            'l': cv2.calcHist(channels=[0], images=[gray], mask=mask,
                              histSize=[256], ranges=[0, 256]).flatten(),
        })

    def reset_sliders(self):
        """Reset all slider handles to neutral (0 / 1.00 / 255) without
        emitting any levels signal — used after reset or image load."""
        for ch, sliders in self._sliders.items():
            # Block signals so we don't trigger preview/commit during reset
            for s in sliders.values():
                s.blockSignals(True)
            sliders['black'].setValue(0)
            sliders['gamma'].setValue(100)
            sliders['white'].setValue(255)
            for s in sliders.values():
                s.blockSignals(False)
        # Force the value labels to update
        self.update()

    def get_channel_levels(self, ch: str) -> tuple[int, float, int]:
        """Return (black, gamma_float, white) for the given channel group.

        ch: 'all' | 'r' | 'g' | 'b'
        gamma is returned as a float (slider_value / 100.0).
        white is clamped to be at least black + 1.
        """
        s     = self._sliders[ch]
        black = s['black'].value()
        gamma = s['gamma'].value() / 100.0
        white = max(s['white'].value(), black + 1)
        return black, gamma, white


    @staticmethod
    def _fmt_val(param: str, v: int) -> str:
        if param == 'gamma':
            return f'{v / 100:.2f}'
        return str(v)

    def _get_values(self, ch: str):
        """Return (black, gamma_float, white) for the given channel."""
        s     = self._sliders[ch]
        black = s['black'].value()
        gamma = s['gamma'].value() / 100.0
        white = s['white'].value()
        # Clamp: white must be > black
        white = max(white, black + 1)
        return black, gamma, white

    def _emit(self, ch: str, kind: str):
        black, gamma, white = self._get_values(ch)
        if kind == 'preview':
            self.levels_preview.emit(ch, black, gamma, white)
        else:
            self.levels_commit.emit(ch, black, gamma, white)

    def _on_reset(self):
        self.reset_sliders()
        self.levels_reset.emit()
