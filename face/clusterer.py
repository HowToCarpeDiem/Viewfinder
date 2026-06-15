"""
face/clusterer.py
=================
HDBSCAN-based face clustering on ArcFace embeddings.

ArcFace embeddings are L2-normalised unit vectors, so cosine distance is
equivalent to (2 - 2·dot) but HDBSCAN natively supports 'cosine' metric,
which is the most meaningful distance for face identity comparison.
"""

import numpy as np

try:
    import hdbscan  # type: ignore
    _HDBSCAN_AVAILABLE = True
except ImportError:
    _HDBSCAN_AVAILABLE = False


def cluster_faces(
    embeddings: np.ndarray,
    min_cluster_size: int = 2,
    min_samples: int = 1,
) -> np.ndarray:
    """Cluster face embeddings with HDBSCAN.

    Parameters
    ----------
    embeddings : np.ndarray
        Shape (N, 512), float32, L2-normalised ArcFace embeddings.
    min_cluster_size : int
        Minimum number of faces to form a cluster.  Faces in groups
        smaller than this are labelled −1 (noise / unclassified).
    min_samples : int
        Controls noise sensitivity.  Larger values → more points become
        noise.  Default 1 keeps most faces assigned.

    Returns
    -------
    np.ndarray
        Integer labels, shape (N,).  −1 means unclassified (noise).
    """
    n = len(embeddings)
    if n == 0:
        return np.array([], dtype=np.int32)

    if n == 1:
        # Single face — assign to cluster 0 regardless of min_cluster_size
        return np.array([0], dtype=np.int32)

    if not _HDBSCAN_AVAILABLE:
        raise RuntimeError(
            "hdbscan is not installed.  Run: pip install hdbscan"
        )

    # Guard: if fewer faces than min_cluster_size, lower the threshold
    # so we still produce at least one cluster.
    effective_min = min(min_cluster_size, n)

    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=effective_min,
        min_samples=min_samples,
        metric='euclidean',            # ArcFace embeddings are L2-normalised unit vectors,
                                       # so euclidean distance is monotonically equivalent
                                       # to cosine distance — identical clustering results.
        cluster_selection_method='eom',
        prediction_data=False,
    )
    labels = clusterer.fit_predict(embeddings.astype(np.float64))
    return labels.astype(np.int32)
