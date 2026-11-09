from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt

from .i18n import render


class FileListModel(QAbstractListModel):
    entry_role = int(Qt.ItemDataRole.UserRole) + 1

    def __init__(self, parent=None):
        super().__init__(parent)
        self.entries = []
        self.loaded = 0
        self.language = "en"
        self.marked = set()
        self.cut = set()

    def roleNames(self):
        return {self.entry_role: b"entry"}

    def rowCount(self, parent=None):
        return 0 if parent is not None and parent.isValid() else self.loaded

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < self.loaded or role != self.entry_role:
            return None
        entry = self.entries[index.row()]
        return render({**entry, "marked": entry["id"] in self.marked, "cut": entry["id"] in self.cut}, self.language)

    def canFetchMore(self, parent=None):
        return (parent is None or not parent.isValid()) and self.loaded < len(self.entries)

    def fetchMore(self, parent=None):
        if not self.canFetchMore(parent):
            return
        end = min(len(self.entries), self.loaded + 200)
        self.beginInsertRows(QModelIndex(), self.loaded, end - 1)
        self.loaded = end
        self.endInsertRows()

    def set_entries(self, entries):
        if entries == self.entries:
            return
        self.beginResetModel()
        self.entries = list(entries)
        self.loaded = min(200, len(self.entries))
        self.endResetModel()

    def ensure_index(self, index):
        while self.canFetchMore() and index >= self.loaded:
            self.fetchMore()

    def set_marks(self, marked, cut=()):
        marked, cut = set(marked), set(cut)
        if (self.marked, self.cut) != (marked, cut):
            self.marked, self.cut = marked, cut
            self.refresh()

    def set_language(self, language):
        if self.language != language:
            self.language = language
            self.refresh()

    def refresh(self):
        if self.loaded:
            self.dataChanged.emit(self.index(0), self.index(self.loaded - 1), [self.entry_role])
