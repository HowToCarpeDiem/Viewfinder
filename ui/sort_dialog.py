"""
ui/sort_dialog.py
=================
Dialog for configuring sort / copy destination folders assigned to keys 1–0.

Configuration is persisted across sessions in:
    ~/.viewfinder/sort_config.json
"""

import json
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QCheckBox, QDialogButtonBox,
    QFileDialog, QFrame, QScrollArea, QWidget,
)
from PySide6.QtCore import Qt


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

_CONFIG_PATH = Path.home() / '.viewfinder' / 'sort_config.json'

# Keys in display order — '0' last (phone-pad convention)
SORT_KEYS = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0']


def load_sort_config() -> dict:
    """Load sort configuration from disk.

    Returns a dict with keys:
        slots     dict[str, str]   key → folder path (empty = unassigned)
        move_mode bool             True = move, False = copy
    """
    try:
        if _CONFIG_PATH.exists():
            with open(_CONFIG_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
            slots = {k: data.get('slots', {}).get(k, '') for k in SORT_KEYS}
            return {
                'slots':     slots,
                'move_mode': bool(data.get('move_mode', True)),
            }
    except Exception:
        pass
    return {
        'slots':     {k: '' for k in SORT_KEYS},
        'move_mode': True,
    }


def save_sort_config(slots: dict, move_mode: bool) -> None:
    """Persist sort configuration to disk."""
    try:
        _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump({'slots': slots, 'move_mode': move_mode}, f, indent=2, ensure_ascii=False)
    except Exception as exc:
        print(f'[SortDialog] Could not save config: {exc}')


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------

class SortDialog(QDialog):
    """Modal dialog for assigning destination folders to keys 1–0."""

    def __init__(self, slots: dict, move_mode: bool, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Sort — Destination Folders')
        self.setMinimumWidth(540)
        self.setModal(True)

        ly_outer = QVBoxLayout(self)
        ly_outer.setSpacing(10)
        ly_outer.setContentsMargins(14, 14, 14, 14)

        # ── Header ──────────────────────────────────────────────────────────
        hdr = QLabel(
            'Assign a destination folder to each key (<b>1 – 9, 0</b>).<br>'
            'Press the key while viewing an image to move / copy it there.'
        )
        hdr.setWordWrap(True)
        ly_outer.addWidget(hdr)

        sep_top = QFrame()
        sep_top.setFrameShape(QFrame.HLine)
        sep_top.setFrameShadow(QFrame.Sunken)
        ly_outer.addWidget(sep_top)

        # ── Slots grid ──────────────────────────────────────────────────────
        grid_widget = QWidget()
        grid = QGridLayout(grid_widget)
        grid.setSpacing(6)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setColumnMinimumWidth(0, 36)   # key badge
        grid.setColumnStretch(1, 1)         # path field
        grid.setColumnMinimumWidth(2, 36)   # browse button

        # Column headers
        hdr_key  = QLabel('<b>Key</b>')
        hdr_key.setAlignment(Qt.AlignCenter)
        hdr_path = QLabel('<b>Destination folder</b>')
        grid.addWidget(hdr_key,  0, 0)
        grid.addWidget(hdr_path, 0, 1)

        self._edits: dict[str, QLineEdit] = {}

        for row, key in enumerate(SORT_KEYS, start=1):
            # Key badge
            badge = QLabel(key)
            badge.setAlignment(Qt.AlignCenter)
            badge.setStyleSheet(
                'font-weight: bold; font-size: 13px;'
                'border: 1px solid #aaa; border-radius: 4px; padding: 2px 6px;'
            )
            grid.addWidget(badge, row, 0)

            # Path input
            edit = QLineEdit(slots.get(key, ''))
            edit.setPlaceholderText('(not assigned)')
            self._edits[key] = edit
            grid.addWidget(edit, row, 1)

            # Browse button
            btn = QPushButton('…')
            btn.setFixedWidth(34)
            btn.setToolTip(f'Browse for folder  (key {key})')
            btn.clicked.connect(lambda _=False, k=key: self._browse(k))
            grid.addWidget(btn, row, 2)

        ly_outer.addWidget(grid_widget)

        # ── Separator ───────────────────────────────────────────────────────
        sep_bot = QFrame()
        sep_bot.setFrameShape(QFrame.HLine)
        sep_bot.setFrameShadow(QFrame.Sunken)
        ly_outer.addWidget(sep_bot)

        # ── Move / copy toggle ───────────────────────────────────────────────
        self._chk_move = QCheckBox('Move files   (uncheck to copy instead)')
        self._chk_move.setChecked(move_mode)
        ly_outer.addWidget(self._chk_move)

        # ── OK / Cancel ─────────────────────────────────────────────────────
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        ly_outer.addWidget(btn_box)

    # ── Internal helpers ────────────────────────────────────────────────────

    def _browse(self, key: str) -> None:
        start = self._edits[key].text().strip() or ''
        folder = QFileDialog.getExistingDirectory(
            self, f'Select destination folder for key  {key}', start
        )
        if folder:
            self._edits[key].setText(folder)

    # ── Public accessors ────────────────────────────────────────────────────

    def get_slots(self) -> dict:
        """Return the current key → path mapping."""
        return {k: edit.text().strip() for k, edit in self._edits.items()}

    def get_move_mode(self) -> bool:
        """True = move files, False = copy files."""
        return self._chk_move.isChecked()
