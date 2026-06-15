"""
face/analyzer.py
================
Thin wrapper around insightface FaceAnalysis that:
  - Uses the locally stored buffalo_l model (no network access at runtime).
  - Selects CPU or GPU (CUDA) ONNX Runtime backend.
  - Returns plain Python dicts so the rest of the app stays framework-agnostic.
"""

from pathlib import Path
from typing import Literal

import numpy as np

# The project's models/ directory is two levels up from this file.
# insightface looks for models at: <root>/models/<name>/*.onnx
_PROJECT_ROOT = Path(__file__).parent.parent
_MODEL_NAME   = 'buffalo_l'

# Only load detection + recognition — skip landmark / gender-age models to
# save memory and speed up initialisation.
_ALLOWED = ['detection', 'recognition']

ProviderType = Literal['cpu', 'gpu']


class FaceAnalyzer:
    """Detects faces and extracts ArcFace embeddings using insightface.

    Parameters
    ----------
    provider : 'cpu' | 'gpu'
        'gpu' requires onnxruntime-gpu and a CUDA-capable GPU.
    """

    def __init__(self, provider: ProviderType = 'cpu'):
        # Import here so the rest of the app can be imported even if insightface
        # is not installed (e.g. for unit tests of unrelated modules).
        from insightface.app import FaceAnalysis  # type: ignore

        onnx_providers = (
            ['CUDAExecutionProvider', 'CPUExecutionProvider']
            if provider == 'gpu'
            else ['CPUExecutionProvider']
        )
        # ctx_id: 0 = first GPU, -1 = CPU
        ctx_id = 0 if provider == 'gpu' else -1

        self._app = FaceAnalysis(
            name=_MODEL_NAME,
            root=str(_PROJECT_ROOT),
            allowed_modules=_ALLOWED,
            providers=onnx_providers,
        )
        # det_size: resolution at which the detector runs.
        # 640×640 is the default and a good balance for family photos.
        self._app.prepare(ctx_id=ctx_id, det_size=(640, 640))

    def analyze(self, img_bgr: np.ndarray) -> list[dict]:
        """Detect all faces in *img_bgr* and return their embeddings.

        Parameters
        ----------
        img_bgr : np.ndarray
            OpenCV image in BGR format (uint8).

        Returns
        -------
        list of dicts, each containing:
            bbox        (x, y, w, h) — bounding box in image pixels (ints)
            confidence  float        — detection score from RetinaFace
            embedding   np.ndarray   — shape (512,) float32, L2-normalised
        """
        raw_faces = self._app.get(img_bgr)
        result: list[dict] = []
        for face in raw_faces:
            x1, y1, x2, y2 = face.bbox.astype(int)
            w, h = x2 - x1, y2 - y1
            # Skip detections that are too small to be reliable.
            if w < 20 or h < 20:
                continue
            if face.normed_embedding is None:
                continue
            result.append({
                'bbox':       (x1, y1, w, h),
                'confidence': float(face.det_score),
                'embedding':  face.normed_embedding.astype(np.float32),
            })
        return result
