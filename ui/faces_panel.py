"""
ui/faces_panel.py
=================
Left-panel tab "Faces":
  - Shows model availability and GPU/CPU selector.
  - "Analyze" button starts the background FaceWorker.
  - After analysis, shows a scrollable grid of person clusters.
  - Clicking a cluster card emits cluster_selected(list[str]) with the
    image paths that contain at least one face from that cluster.
  - Double-clicking a card lets the user name the person.
  - "Re-analyze" button re-runs clustering (faces already in cache are
    not re-detected, only clustering is redone).
"""

import os
import cv2
import numpy as np
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QProgressBar, QScrollArea, QGridLayout, QFrame, QComboBox,
    QSizePolicy, QInputDialog, QMessageBox,
)
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtCore import Qt, Signal

from face.cache import FaceCache
from face.worker import FaceWorker
from face.clusterer import cluster_faces

# Constants

_PROJECT_ROOT = Path(__file__).parent.parent
_MODEL_DIR    = _PROJECT_ROOT / 'models' / 'buffalo_l'
_REQUIRED_ONNX = {'det_10g.onnx', 'w600k_r50.onnx'}

THUMB_SIZE = 84   # pixel side of each face thumbnail

_BTN_STYLE = """
QPushButton {
    border: 1px solid #c0c0c0;
    border-radius: 4px;
    padding: 4px 8px;
    background-color: transparent;
    font-size: 11px;
}
QPushButton:hover    { background-color: #dbe9f9; border-color: #88b4e0; }
QPushButton:pressed  { background-color: #b3d4f5; }
QPushButton:disabled { color: #aaa; border-color: #ddd; }
"""


# ClusterCard

class ClusterCard(QFrame):
    """Thumbnail card representing one face cluster (= one person)."""

    clicked = Signal(int)         # cluster label
    renamed = Signal(int, str)    # cluster label, new name

    _NORMAL_STYLE = """
        ClusterCard {
            border: 2px solid #d0d0d0;
            border-radius: 6px;
            background: #f8f8f8;
        }
        ClusterCard:hover {
            border-color: #4a9be8;
            background: #edf5ff;
        }
    """
    _SELECTED_STYLE = """
        ClusterCard {
            border: 2px solid #1a6fbe;
            border-radius: 6px;
            background: #d0e8ff;
        }
    """

    def __init__(
        self,
        label: int,
        name: str,
        face_count: int,
        thumb_pixmap: QPixmap,
        parent=None,
    ):
        super().__init__(parent)
        self._label    = label
        self._selected = False

        self.setFrameShape(QFrame.StyledPanel)
        self.setFixedWidth(THUMB_SIZE + 12)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(self._NORMAL_STYLE)

        ly = QVBoxLayout(self)
        ly.setContentsMargins(4, 4, 4, 4)
        ly.setSpacing(2)

        # Thumbnail
        self._lbl_thumb = QLabel()
        self._lbl_thumb.setFixedSize(THUMB_SIZE, THUMB_SIZE)
        self._lbl_thumb.setAlignment(Qt.AlignCenter)
        self._lbl_thumb.setStyleSheet('background: #e0e0e0; border-radius: 3px;')
        if not thumb_pixmap.isNull():
            self._lbl_thumb.setPixmap(
                thumb_pixmap.scaled(
                    THUMB_SIZE, THUMB_SIZE,
                    Qt.KeepAspectRatioByExpanding,
                    Qt.SmoothTransformation,
                )
            )
        else:
            self._lbl_thumb.setText('?')
        ly.addWidget(self._lbl_thumb)

        # Photo count
        lbl_count = QLabel(f'{face_count} photo{"s" if face_count != 1 else ""}')
        lbl_count.setAlignment(Qt.AlignCenter)
        lbl_count.setStyleSheet('font-size: 9px; color: #888;')
        ly.addWidget(lbl_count)

        # Person name (double-click to edit)
        self.lbl_name = QLabel(name or f'Person {label + 1}')
        self.lbl_name.setAlignment(Qt.AlignCenter)
        self.lbl_name.setStyleSheet('font-size: 10px; font-weight: bold; color: #333;')
        self.lbl_name.setWordWrap(True)
        ly.addWidget(self.lbl_name)

    # Selection visual

    def set_selected(self, selected: bool):
        self._selected = selected
        self.setStyleSheet(
            self._SELECTED_STYLE if selected else self._NORMAL_STYLE
        )

    # Mouse events

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self._label)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            current = self.lbl_name.text()
            name, ok = QInputDialog.getText(
                self, 'Name this person', 'Name:', text=current
            )
            if ok and name.strip():
                name = name.strip()
                self.lbl_name.setText(name)
                self.renamed.emit(self._label, name)
        super().mouseDoubleClickEvent(event)


# FacesPanel

class FacesPanel(QWidget):
    """Panel for face analysis, cluster browsing, and navigation."""

    # Emitted when the user clicks a cluster card.
    # Carries the list of image paths containing that person.
    cluster_selected = Signal(list)

    # Emitted when the user deselects (clicks the same card again).
    cluster_cleared  = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self._cache       : FaceCache | None  = None
        self._worker      : FaceWorker | None = None
        self._image_paths : list[str]         = []
        self._cards       : dict[int, ClusterCard] = {}
        self._selected_label: int | None      = None

        ly = QVBoxLayout(self)
        ly.setContentsMargins(4, 6, 4, 4)
        ly.setSpacing(6)

        # Model status
        model_ok = self._model_ready()
        _color   = '#2a7a2a' if model_ok else '#bb2222'
        _text    = '✓ Model ready' if model_ok else '✗ Model missing\nRun: python download_models.py'
        self.lbl_model = QLabel(_text)
        self.lbl_model.setWordWrap(True)
        self.lbl_model.setStyleSheet(f'font-size: 10px; color: {_color};')
        ly.addWidget(self.lbl_model)

        # Device selector
        ly_prov = QHBoxLayout()
        ly_prov.addWidget(QLabel('Device:'))
        self.combo_device = QComboBox()
        self.combo_device.addItems(['CPU', 'GPU (CUDA)'])
        self.combo_device.setStyleSheet('font-size: 11px;')
        self.combo_device.setFixedHeight(24)
        ly_prov.addWidget(self.combo_device)
        ly_prov.addStretch()
        ly.addLayout(ly_prov)

        # Action buttons
        ly_btns = QHBoxLayout()
        self.btn_analyze = QPushButton('Analyze Faces')
        self.btn_analyze.setStyleSheet(_BTN_STYLE)
        self.btn_analyze.setEnabled(model_ok)
        self.btn_analyze.clicked.connect(self._start_analysis)
        ly_btns.addWidget(self.btn_analyze)

        self.btn_recluster = QPushButton('Re-cluster')
        self.btn_recluster.setStyleSheet(_BTN_STYLE)
        self.btn_recluster.setEnabled(False)
        self.btn_recluster.setToolTip(
            'Re-run HDBSCAN on all cached embeddings\n'
            '(does not re-detect faces)'
        )
        self.btn_recluster.clicked.connect(self._recluster)
        ly_btns.addWidget(self.btn_recluster)
        ly.addLayout(ly_btns)

        # Status / progress
        self.lbl_status = QLabel('Open a directory to start.')
        self.lbl_status.setStyleSheet('font-size: 10px; color: #555;')
        self.lbl_status.setWordWrap(True)
        ly.addWidget(self.lbl_status)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedHeight(14)
        self.progress_bar.setTextVisible(False)
        ly.addWidget(self.progress_bar)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        ly.addWidget(sep)

        # People header
        self.lbl_people = QLabel('No analysis yet.')
        self.lbl_people.setStyleSheet('font-size: 10px; color: #777;')
        ly.addWidget(self.lbl_people)

        # Cluster grid (scrollable)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._grid_widget = QWidget()
        self._grid_layout = QGridLayout(self._grid_widget)
        self._grid_layout.setSpacing(6)
        self._grid_layout.setContentsMargins(2, 2, 2, 2)
        self._grid_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        self._scroll.setWidget(self._grid_widget)
        ly.addWidget(self._scroll, stretch=1)

    # Public API

    def set_directory(self, image_paths: list[str], directory: str):
        """Called by MainWindow whenever a new directory is opened."""
        self._image_paths = image_paths
        db_path = os.path.join(directory, '.viewfinder_faces.db')

        if self._cache:
            self._cache.close()
        self._cache = FaceCache(db_path)

        n = len(image_paths)
        self.lbl_status.setText(f'{n} image{"s" if n != 1 else ""} in directory.')
        self.btn_analyze.setEnabled(self._model_ready())
        self._selected_label = None

        # Show any already-cached results from a previous session
        self._refresh_grid()

    # Private helpers

    @staticmethod
    def _model_ready() -> bool:
        if not _MODEL_DIR.exists():
            return False
        present = {f.name for f in _MODEL_DIR.glob('*.onnx')}
        return _REQUIRED_ONNX.issubset(present)

    def _provider(self) -> str:
        return 'gpu' if self.combo_device.currentIndex() == 1 else 'cpu'

    # Analysis

    def _start_analysis(self):
        if not self._image_paths or self._cache is None:
            return
        if self._worker and self._worker.isRunning():
            self._worker.abort()
            return

        self._set_running(True)

        self._worker = FaceWorker(
            self._image_paths, self._cache, provider=self._provider()
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.status.connect(self.lbl_status.setText)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _recluster(self):
        """Re-run HDBSCAN without re-detecting faces."""
        if self._cache is None:
            return
        self.lbl_status.setText('Re-clustering…')
        face_ids, embeddings = self._cache.get_all_embeddings()
        if len(face_ids) > 0:
            labels = cluster_faces(embeddings)
            self._cache.update_clusters(face_ids, labels.tolist())
        self.lbl_status.setText('Done.')
        self._refresh_grid()

    # Worker slots

    def _on_progress(self, done: int, total: int):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(done)

    def _on_finished(self):
        self._set_running(False)
        self._refresh_grid()

    def _on_error(self, msg: str):
        self._set_running(False)
        self.lbl_status.setText(f'Error: {msg}')
        QMessageBox.critical(self, 'Face Analysis Error', msg)

    def _set_running(self, running: bool):
        self.progress_bar.setVisible(running)
        if running:
            self.btn_analyze.setText('Cancel')
            self.btn_recluster.setEnabled(False)
        else:
            self.btn_analyze.setText('Analyze Faces')
            self.btn_analyze.setEnabled(self._model_ready())
            self.btn_recluster.setEnabled(True)
            self.progress_bar.setValue(0)

    # Grid

    def _refresh_grid(self):
        """Clear and rebuild the cluster thumbnail grid from the cache."""
        # Remove old cards
        for i in reversed(range(self._grid_layout.count())):
            item = self._grid_layout.itemAt(i)
            if item and item.widget():
                item.widget().deleteLater()
        self._cards.clear()

        if self._cache is None:
            return

        clusters = self._cache.get_clusters()
        if not clusters:
            self.lbl_people.setText('No faces detected yet.')
            return

        n_people = len(clusters)
        n_noise  = sum(
            1 for c in clusters if c['label'] == -1
        )
        n_people_real = n_people - (1 if n_noise else 0)
        self.lbl_people.setText(
            f'{n_people_real} person{"s" if n_people_real != 1 else ""} found.'
        )

        cols = 2
        for idx, cl in enumerate(clusters):
            if cl['label'] == -1:
                continue   # skip noise cluster
            thumb = self._load_face_thumb(cl['image_path'], cl['bbox'])
            card = ClusterCard(
                label=cl['label'],
                name=cl['name'] or '',
                face_count=cl['face_count'],
                thumb_pixmap=thumb,
            )
            card.clicked.connect(self._on_card_clicked)
            card.renamed.connect(self._on_card_renamed)

            if cl['label'] == self._selected_label:
                card.set_selected(True)

            self._cards[cl['label']] = card
            self._grid_layout.addWidget(card, idx // cols, idx % cols)

    def _load_face_thumb(self, image_path: str, bbox: tuple) -> QPixmap:
        """Crop a padded face region from an image and return as QPixmap."""
        try:
            img = cv2.imread(image_path)
            if img is None:
                return QPixmap()
            x, y, w, h = bbox
            pad = int(max(w, h) * 0.25)
            x0  = max(0, x - pad)
            y0  = max(0, y - pad)
            x1  = min(img.shape[1], x + w + pad)
            y1  = min(img.shape[0], y + h + pad)
            crop = img[y0:y1, x0:x1]
            if crop.size == 0:
                return QPixmap()
            rgb  = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
            h2, w2 = rgb.shape[:2]
            return QPixmap.fromImage(
                QImage(rgb.data, w2, h2, w2 * 3, QImage.Format_RGB888)
            )
        except Exception:
            return QPixmap()

    # Card interaction

    def _on_card_clicked(self, label: int):
        if self._cache is None:
            return

        if self._selected_label == label:
            # Second click on the same card → deselect
            self._selected_label = None
            for card in self._cards.values():
                card.set_selected(False)
            self.cluster_cleared.emit()
            return

        # Select new card
        self._selected_label = label
        for lbl, card in self._cards.items():
            card.set_selected(lbl == label)

        paths = self._cache.get_image_paths_for_cluster(label)
        self.cluster_selected.emit(paths)

    def _on_card_renamed(self, label: int, name: str):
        if self._cache:
            self._cache.rename_cluster(label, name)
