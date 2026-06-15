"""
face/worker.py
==============
QThread worker that:
  1. Iterates over a list of image paths.
  2. Skips images already present in the SQLite cache (cache hit by mtime).
  3. Runs RetinaFace + ArcFace on each new / changed image.
  4. After all images are processed, runs HDBSCAN on all embeddings.
  5. Writes results back to the cache.

All signals are emitted from the worker thread, so UI slots must be
connected via Qt's queued connection (the default for cross-thread signals).
"""

import cv2
from PySide6.QtCore import QThread, Signal

from face.cache import FaceCache
from face.analyzer import FaceAnalyzer, ProviderType
from face.clusterer import cluster_faces


class FaceWorker(QThread):
    """Background worker for face detection, embedding, and clustering."""

    # (images_done, images_total)
    progress = Signal(int, int)

    # Human-readable status message for the UI label
    status = Signal(str)

    # Emitted when all work is complete (clustering finished)
    finished = Signal()

    # Emitted on unrecoverable errors; argument is the error message
    error = Signal(str)

    def __init__(
        self,
        image_paths: list[str],
        cache: FaceCache,
        provider: ProviderType = 'cpu',
        parent=None,
    ):
        super().__init__(parent)
        self._paths    = image_paths
        self._cache    = cache
        self._provider = provider
        self._abort    = False

    def abort(self):
        """Request graceful cancellation.  The thread stops after the
        current image finishes processing."""
        self._abort = True

    # QThread entry point

    def run(self):
        try:
            self._run()
        except Exception as exc:
            self.error.emit(str(exc))

    def _run(self):
        # 1. Load model
        self.status.emit('Loading model…')
        try:
            analyzer = FaceAnalyzer(self._provider)
        except Exception as exc:
            self.error.emit(f'Model load failed: {exc}')
            return

        # 2. Process images
        total = len(self._paths)
        done  = 0

        for path in self._paths:
            if self._abort:
                self.status.emit('Cancelled.')
                return

            done += 1

            # Cache hit — skip expensive inference
            if self._cache.is_image_cached(path):
                self.progress.emit(done, total)
                continue

            # Load image
            img = cv2.imread(path)
            if img is None:
                self.progress.emit(done, total)
                continue

            h, w = img.shape[:2]
            image_id = self._cache.upsert_image(path, w, h)

            # Detect + embed
            try:
                faces = analyzer.analyze(img)
                self._cache.save_faces(image_id, faces)
            except Exception as exc:
                print(f'[FaceWorker] {path}: {exc}')
                self._cache.mark_error(image_id)

            self.status.emit(f'Processing {done}/{total}…')
            self.progress.emit(done, total)

        if self._abort:
            self.status.emit('Cancelled.')
            return

        # 3. Cluster all embeddings
        self.status.emit('Clustering faces…')
        face_ids, embeddings = self._cache.get_all_embeddings()

        if len(face_ids) > 0:
            labels = cluster_faces(embeddings)
            self._cache.update_clusters(face_ids, labels.tolist())

        self.status.emit('Done.')
        self.finished.emit()
