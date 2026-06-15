"""
face/cache.py
=============
SQLite-backed cache for face detections and embeddings.

One database per directory, stored as:
    <directory>/.viewfinder_faces.db

Schema
------
images   — one row per image file; invalidated by mtime change.
faces    — one row per detected face with its 512-dim ArcFace embedding.
clusters — one row per HDBSCAN cluster with a representative face.
"""

import os
import sqlite3
from typing import Optional

import numpy as np

_SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS images (
    id        INTEGER PRIMARY KEY,
    path      TEXT    UNIQUE NOT NULL,
    mtime     REAL    NOT NULL,
    width     INTEGER,
    height    INTEGER,
    processed INTEGER DEFAULT 0   -- 0=pending  1=ok  2=error
);

CREATE TABLE IF NOT EXISTS faces (
    id          INTEGER PRIMARY KEY,
    image_id    INTEGER NOT NULL
                    REFERENCES images(id) ON DELETE CASCADE,
    bbox_x      INTEGER NOT NULL,
    bbox_y      INTEGER NOT NULL,
    bbox_w      INTEGER NOT NULL,
    bbox_h      INTEGER NOT NULL,
    confidence  REAL    NOT NULL,
    embedding   BLOB    NOT NULL,   -- 512 × float32  (2 048 bytes)
    cluster_id  INTEGER DEFAULT -1
);

CREATE TABLE IF NOT EXISTS clusters (
    id                  INTEGER PRIMARY KEY,
    label               INTEGER UNIQUE NOT NULL,
    name                TEXT,
    representative_face INTEGER REFERENCES faces(id)
);

CREATE INDEX IF NOT EXISTS idx_faces_image   ON faces(image_id);
CREATE INDEX IF NOT EXISTS idx_faces_cluster ON faces(cluster_id);
"""

_EMBED_DIM = 512


class FaceCache:
    """Thread-safe (single-thread) SQLite face cache."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    # Connection

    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.executescript(_SCHEMA)
            self._conn.commit()
        return self._conn

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    def _init_db(self):
        self._connect()

    # Images

    def is_image_cached(self, path: str) -> bool:
        """Return True if the image has already been processed and its
        file has not been modified since (mtime matches)."""
        conn = self._connect()
        row = conn.execute(
            "SELECT mtime, processed FROM images WHERE path = ?", (path,)
        ).fetchone()
        if row is None:
            return False
        try:
            current_mtime = os.path.getmtime(path)
        except OSError:
            return False
        return abs(row[0] - current_mtime) < 0.01 and row[1] == 1

    def upsert_image(self, path: str, width: int, height: int) -> int:
        """Insert or update the image record.  Returns the row id."""
        conn = self._connect()
        mtime = os.path.getmtime(path)
        conn.execute(
            """
            INSERT INTO images (path, mtime, width, height, processed)
            VALUES (?, ?, ?, ?, 0)
            ON CONFLICT(path) DO UPDATE SET
                mtime     = excluded.mtime,
                width     = excluded.width,
                height    = excluded.height,
                processed = 0
            """,
            (path, mtime, width, height),
        )
        conn.commit()
        return conn.execute(
            "SELECT id FROM images WHERE path = ?", (path,)
        ).fetchone()[0]

    def mark_error(self, image_id: int):
        """Mark the image as failed (processed = 2)."""
        conn = self._connect()
        conn.execute(
            "UPDATE images SET processed = 2 WHERE id = ?", (image_id,)
        )
        conn.commit()

    # Faces

    def save_faces(self, image_id: int, faces: list):
        """Replace all faces for this image and mark it as processed.

        Each item in *faces* must have:
            bbox        (x, y, w, h) ints
            confidence  float
            embedding   np.ndarray shape (512,) float32
        """
        conn = self._connect()
        conn.execute("DELETE FROM faces WHERE image_id = ?", (image_id,))
        for f in faces:
            blob = np.asarray(f['embedding'], dtype=np.float32).tobytes()
            conn.execute(
                """
                INSERT INTO faces
                    (image_id, bbox_x, bbox_y, bbox_w, bbox_h,
                     confidence, embedding)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    image_id,
                    int(f['bbox'][0]), int(f['bbox'][1]),
                    int(f['bbox'][2]), int(f['bbox'][3]),
                    float(f['confidence']),
                    blob,
                ),
            )
        conn.execute(
            "UPDATE images SET processed = 1 WHERE id = ?", (image_id,)
        )
        conn.commit()

    def get_all_embeddings(self) -> tuple[list[int], np.ndarray]:
        """Return (face_ids, embeddings) for all stored faces.

        embeddings shape: (N, 512) float32.
        """
        conn = self._connect()
        rows = conn.execute("SELECT id, embedding FROM faces").fetchall()
        if not rows:
            return [], np.empty((0, _EMBED_DIM), dtype=np.float32)
        face_ids = [r[0] for r in rows]
        raw = b''.join(r[1] for r in rows)
        embeddings = np.frombuffer(raw, dtype=np.float32).reshape(
            len(rows), _EMBED_DIM
        )
        return face_ids, embeddings

    # Clusters

    def update_clusters(self, face_ids: list[int], labels: list[int]):
        """Write HDBSCAN labels back into the faces table and rebuild
        the clusters table with one representative face per cluster."""
        conn = self._connect()
        conn.execute("DELETE FROM clusters")

        # Batch-update cluster_id on faces
        conn.executemany(
            "UPDATE faces SET cluster_id = ? WHERE id = ?",
            zip(labels, face_ids),
        )

        # One cluster row per unique non-noise label
        seen: dict[int, int] = {}   # label → first face_id encountered
        for fid, lbl in zip(face_ids, labels):
            if lbl >= 0 and lbl not in seen:
                seen[lbl] = fid

        conn.executemany(
            """
            INSERT INTO clusters (label, representative_face)
            VALUES (?, ?)
            ON CONFLICT(label) DO UPDATE SET
                representative_face = excluded.representative_face
            """,
            seen.items(),
        )
        conn.commit()

    def get_clusters(self) -> list[dict]:
        """Return all clusters sorted by descending face count.

        Each dict contains:
            label           int   (HDBSCAN label, ≥ 0)
            name            str | None
            rep_face_id     int
            image_path      str
            bbox            (x, y, w, h)
            face_count      int   (number of photos containing this person)
        """
        conn = self._connect()
        rows = conn.execute(
            """
            SELECT
                c.label,
                c.name,
                c.representative_face,
                i.path,
                rf.bbox_x, rf.bbox_y, rf.bbox_w, rf.bbox_h,
                COUNT(DISTINCT f.image_id) AS face_count
            FROM clusters c
            JOIN faces  rf ON rf.id       = c.representative_face
            JOIN images i  ON i.id        = rf.image_id
            JOIN faces  f  ON f.cluster_id = c.label
            GROUP BY c.label
            ORDER BY face_count DESC
            """
        ).fetchall()
        return [
            {
                'label':       r[0],
                'name':        r[1],
                'rep_face_id': r[2],
                'image_path':  r[3],
                'bbox':        (r[4], r[5], r[6], r[7]),
                'face_count':  r[8],
            }
            for r in rows
        ]

    def get_image_paths_for_cluster(self, label: int) -> list[str]:
        """Return all distinct image paths that contain at least one
        face belonging to *label*."""
        conn = self._connect()
        rows = conn.execute(
            """
            SELECT DISTINCT i.path
            FROM   faces  f
            JOIN   images i ON i.id = f.image_id
            WHERE  f.cluster_id = ?
            ORDER BY i.path
            """,
            (label,),
        ).fetchall()
        return [r[0] for r in rows]

    def rename_cluster(self, label: int, name: str):
        conn = self._connect()
        conn.execute(
            "UPDATE clusters SET name = ? WHERE label = ?", (name, label)
        )
        conn.commit()

    def clear_clusters(self):
        """Reset all cluster assignments (useful before re-clustering)."""
        conn = self._connect()
        conn.execute("DELETE FROM clusters")
        conn.execute("UPDATE faces SET cluster_id = -1")
        conn.commit()
