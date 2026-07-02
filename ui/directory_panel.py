import os

from PySide6.QtWidgets import QWidget, QVBoxLayout, QTreeWidget, QTreeWidgetItem, QLabel
from PySide6.QtCore import Qt, Signal


IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.gif', '.webp'}


class DirectoryPanel(QWidget):
    """
    Shows a directory tree with image files (recursive).
    Emits file_selected(path) when the user double-clicks a file.
    """

    file_selected   = Signal(str)   # emitted when user double-clicks an image file
    folder_selected = Signal(str)   # emitted when user double-clicks a directory

    def __init__(self, parent=None):
        super().__init__(parent)

        ly = QVBoxLayout(self)
        ly.setContentsMargins(4, 4, 4, 4)
        ly.setSpacing(4)

        self._hint = QLabel('Open a directory (File → Open Directory)\nto browse images.')
        self._hint.setWordWrap(True)
        ly.addWidget(self._hint)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabel('Directory')
        self.tree.setColumnCount(1)
        self.tree.hide()
        ly.addWidget(self.tree)

        self._path_to_item: dict[str, QTreeWidgetItem] = {}

        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)


    def load_directory(self, root_path: str):
        """Populate the tree with the directory structure (recursive)."""
        self.tree.clear()
        self._path_to_item.clear()
        self._hint.hide()
        self.tree.show()

        root_item = QTreeWidgetItem([os.path.basename(root_path)])
        root_item.setData(0, Qt.UserRole, root_path)
        self._path_to_item[root_path] = root_item
        self.tree.addTopLevelItem(root_item)

        self._populate_tree(root_item, root_path)
        root_item.setExpanded(True)


    def get_all_images(self, root_path: str) -> list[str]:
        """Return a sorted list of image files directly inside root_path.

        Non-recursive — only files in the given directory are returned.
        To navigate images in a subdirectory the user must click that
        subdirectory in the tree, which calls load_directory on it.
        """
        try:
            entries = os.scandir(root_path)
        except OSError:
            return []
        images = sorted(
            (
                entry.path
                for entry in entries
                if entry.is_file()
                and os.path.splitext(entry.name)[1].lower() in IMAGE_EXTENSIONS
            ),
            key=lambda p: os.path.basename(p).lower(),
        )
        return images


    def highlight_file(self, path: str):
        """Select and scroll to the tree item that corresponds to the given path."""
        item = self._path_to_item.get(path)
        if item:
            self.tree.setCurrentItem(item)
            self.tree.scrollToItem(item)


    def filter_by_paths(self, paths: set):
        """Dim all tree items except those whose path is in *paths*.

        Matching image items are shown normally; non-matching image items
        are shown in a lighter colour.  Directory items are not dimmed.
        """
        from PySide6.QtGui import QColor
        dim_color    = QColor('#b0b0b0')
        normal_color = QColor()          # default (invalid → inherits palette)

        for path, item in self._path_to_item.items():
            if not os.path.isfile(path):
                continue   # directory item — leave untouched
            is_match = path in paths
            item.setForeground(0, normal_color if is_match else dim_color)
            font = item.font(0)
            font.setItalic(not is_match)
            item.setFont(0, font)

        # Scroll to first match
        for path in sorted(paths):
            item = self._path_to_item.get(path)
            if item:
                self.tree.scrollToItem(item)
                break


    def clear_filter(self):
        """Remove any active filter — restore all items to normal appearance."""
        from PySide6.QtGui import QColor
        normal_color = QColor()
        for item in self._path_to_item.values():
            item.setForeground(0, normal_color)
            font = item.font(0)
            font.setItalic(False)
            item.setFont(0, font)


    def _populate_tree(self, parent_item: QTreeWidgetItem, dir_path: str):
        """Recursively build tree items for a directory."""
        try:
            entries = sorted(
                os.scandir(dir_path),
                key=lambda e: (e.is_file(), e.name.lower())
            )
        except PermissionError:
            return

        for entry in entries:
            if entry.is_dir():
                item = QTreeWidgetItem([entry.name])
                item.setData(0, Qt.UserRole, entry.path)
                self._path_to_item[entry.path] = item
                parent_item.addChild(item)
                self._populate_tree(item, entry.path)

            elif entry.is_file():
                if os.path.splitext(entry.name)[1].lower() in IMAGE_EXTENSIONS:
                    item = QTreeWidgetItem([entry.name])
                    item.setData(0, Qt.UserRole, entry.path)
                    self._path_to_item[entry.path] = item
                    parent_item.addChild(item)


    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        path = item.data(0, Qt.UserRole)
        if not path:
            return
        if os.path.isdir(path):
            self.folder_selected.emit(path)
        elif os.path.isfile(path):
            if os.path.splitext(path)[1].lower() in IMAGE_EXTENSIONS:
                self.file_selected.emit(path)