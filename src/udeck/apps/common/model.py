"""Virtualized application cards; serialize only the rows requested by Qt Quick."""

from PySide6.QtCore import QAbstractListModel, Qt

from udeck.i18n import render


class CardListModel(QAbstractListModel):
    entry_role = int(Qt.ItemDataRole.UserRole) + 1

    def __init__(self, parent=None):
        super().__init__(parent)
        self.entries = []
        self.by_id = {}
        self.language = 'en'

    def roleNames(self):
        return {self.entry_role: b'entry'}

    def rowCount(self, parent=None):
        return 0 if parent is not None and parent.isValid() else len(self.entries)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if index.isValid() and 0 <= index.row() < len(self.entries) and role == self.entry_role:
            return render(self.entries[index.row()], self.language)
        return None

    def set_entries(self, entries, language):
        if entries != self.entries:
            self.beginResetModel()
            self.entries = entries
            self.by_id = {}
            for index, entry in enumerate(entries):
                self.by_id.setdefault(entry['id'], index)
            self.language = language
            self.endResetModel()
        elif language != self.language:
            self.language = language
            if self.entries:
                self.dataChanged.emit(self.index(0), self.index(len(self.entries) - 1), [self.entry_role])

    def item(self, identifier):
        index = self.by_id.get(identifier)
        return render(self.entries[index], self.language) if index is not None else {}
