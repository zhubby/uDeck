"""
[INPUT]: 依赖运行服务按应用身份生成的行数据。
[OUTPUT]: 提供含 PSS、RSS 和独占内存的增量 ConsoleModel。
[POS]: Console 的 Qt 列表模型；指标刷新只发送 dataChanged。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt


class ConsoleModel(QAbstractListModel):
    fields = ("applicationKey", "applicationName", "applicationIcon", "runtimeState",
              "cpuPercent", "memoryBytes", "uptimeSeconds", "canQuit", "canForce",
              "memoryRssBytes", "memoryPrivateBytes")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []
        self.roles = {int(Qt.ItemDataRole.UserRole) + index + 1: name for index, name in enumerate(self.fields)}

    def roleNames(self):
        return {role: name.encode() for role, name in self.roles.items()}

    def rowCount(self, parent=None):
        return 0 if parent is not None and parent.isValid() else len(self.rows)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.rows):
            return None
        return self.rows[index.row()].get(self.roles.get(role, ""))

    def update(self, rows):
        wanted = {row["applicationKey"] for row in rows}
        for index in range(len(self.rows) - 1, -1, -1):
            if self.rows[index]["applicationKey"] not in wanted:
                self.beginRemoveRows(QModelIndex(), index, index)
                self.rows.pop(index)
                self.endRemoveRows()
        for index, row in enumerate(rows):
            if index >= len(self.rows) or self.rows[index]["applicationKey"] != row["applicationKey"]:
                self.beginInsertRows(QModelIndex(), index, index)
                self.rows.insert(index, dict(row))
                self.endInsertRows()
            else:
                roles = [role for role, name in self.roles.items() if self.rows[index].get(name) != row.get(name)]
                self.rows[index] = dict(row)
                if roles:
                    self.dataChanged.emit(self.index(index), self.index(index), roles)
