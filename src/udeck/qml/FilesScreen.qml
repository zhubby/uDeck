/*
[INPUT]: 依赖文件模型、目录快照、SelectionViewport和主题。
[OUTPUT]: 提供文件网格、安全区滚动和合并布局。
[POS]: 桌面文件视图；文件操作与选择由控制器决策。
[PROTOCOL]: Update this header on change, then check AGENTS.md
*/
import QtQuick
import QtQuick.Controls

Item {
    id: root
    readonly property var msg: controller.messageKeys
    required property var state
    required property var colors
    required property string fontFamily
    required property string language
    required property var fileModel
    required property int currentIndex
    required property bool contentFocused
    required property bool busy
    property bool reducedMotion: false
    readonly property int columns: Math.max(1, Math.floor(width / 210))
    readonly property bool taskActive: !!state.task.active
    readonly property var current: state.current || {}
    property bool layoutPending: true
    function tr(source) { return controller.translate(source, language) }
    function syncColumns() {
        layoutPending = true
        if (visible) {
            controller.setFileGridColumns(columns)
            Qt.callLater(layoutSelection)
        }
    }
    function invalidateLayout() {
        layoutPending = true
        if (visible) Qt.callLater(layoutSelection)
    }
    function layoutSelection() {
        if (!visible || !layoutPending) return
        layoutPending = false
        fileGrid.forceLayout()
        gridViewport.ensureVisible(true)
        breadcrumbViewport.ensureVisible(true)
    }
    function positionSelection() {
        if (!visible) return
        if (layoutPending) Qt.callLater(layoutSelection)
        else {
            gridViewport.ensureVisible()
            breadcrumbViewport.ensureVisible()
        }
    }
    onColumnsChanged: syncColumns()
    onVisibleChanged: syncColumns()
    Component.onCompleted: syncColumns()
    SelectionViewport {
        id: gridViewport
        view: fileGrid; active: root.visible && !root.layoutPending; reducedMotion: root.reducedMotion
    }
    SelectionViewport {
        id: breadcrumbViewport
        view: breadcrumbs; active: root.visible; reducedMotion: root.reducedMotion
    }
    Connections {
        target: root.fileModel
        function onModelReset() { root.invalidateLayout() }
        function onRowsInserted() { root.invalidateLayout() }
        function onRowsRemoved() { root.invalidateLayout() }
        function onLayoutChanged() { root.invalidateLayout() }
    }

    Rectangle {
        width: parent.width; height: 40; radius: 8; color: root.colors.panel
        ListView {
            id: breadcrumbs
            objectName: "fileBreadcrumbs"
            x: 8; width: parent.width - 16; height: parent.height
            orientation: ListView.Horizontal; spacing: 3; clip: true
            model: root.state.breadcrumbs
            currentIndex: root.state.breadcrumbIndex
            highlightFollowsCurrentItem: false
            interactive: false; keyNavigationEnabled: false
            FocusFrame {
                parent: breadcrumbs.contentItem; target: breadcrumbs.currentItem
                active: root.visible && root.contentFocused && root.state.section === "breadcrumbs"
                accent: root.colors.accent; reducedMotion: root.reducedMotion; radius: 6
            }
            delegate: Rectangle {
                required property var modelData
                required property int index
                readonly property bool focused: root.contentFocused && root.state.section === "breadcrumbs" && root.state.breadcrumbIndex === index
                width: Math.min(190, breadcrumbLabel.implicitWidth + 32); height: 40; radius: 6
                color: focused ? root.colors.selected : "transparent"
                border.width: 0
                Text {
                    id: breadcrumbLabel
                    textFormat: Text.PlainText; anchors.centerIn: parent; width: Math.min(158, implicitWidth)
                    text: modelData.name; elide: Text.ElideMiddle; maximumLineCount: 1; clip: true
                    font.family: root.fontFamily; font.pixelSize: 23
                    color: focused ? root.colors.accent : root.colors.text
                }
            }
        }
    }

    GridView {
        id: fileGrid
        objectName: "fileGrid"
        readonly property real availableHeight: Math.max(120, root.height - y - (root.taskActive ? 118 : 58))
        x: 0; y: 52; width: parent.width
        height: Math.floor(availableHeight / cellHeight) * cellHeight
        cellWidth: width / root.columns
        cellHeight: Math.max(112, Math.min(164, Math.floor(Math.max(120, root.height - y - 58) / 2)))
        model: root.fileModel; currentIndex: root.currentIndex; clip: true
        highlightFollowsCurrentItem: false
        interactive: false; keyNavigationEnabled: false
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar { palette: root.colors.controls; policy: ScrollBar.AsNeeded; interactive: false }
        onWidthChanged: root.invalidateLayout()
        onHeightChanged: root.invalidateLayout()
        FocusFrame {
            objectName: "fileFocus"; parent: fileGrid.contentItem; target: fileGrid.currentItem
            active: root.visible && root.contentFocused && root.state.section === "list"
            accent: root.colors.accent; reducedMotion: root.reducedMotion
            leftInset: 6; rightInset: 6; topInset: 4; bottomInset: 4; radius: 12
        }
        delegate: Item {
            required property var entry
            required property int index
            width: fileGrid.cellWidth; height: fileGrid.cellHeight
            Rectangle {
                id: tile
                objectName: "fileTile"
                readonly property bool current: root.currentIndex === index
                readonly property bool focused: current && root.contentFocused && root.state.section === "list"
                readonly property real iconSize: Math.max(44, Math.min(72, fileGrid.cellHeight - 88))
                x: 6; y: 4; width: parent.width - 12; height: parent.height - 8; radius: 12
                color: current || entry.marked ? root.colors.selected : "transparent"
                border.width: entry.marked ? 1 : 0; border.color: root.colors.border
                opacity: entry.cut ? 0.6 : 1
                Image {
                    id: fileIcon
                    objectName: "fileIcon"
                    anchors.horizontalCenter: parent.horizontalCenter; y: 8
                    width: tile.iconSize; height: width
                    sourceSize: Qt.size(width * 2, height * 2)
                    source: "image://desktop/" + encodeURIComponent(entry.icon || "text-x-generic")
                }
                Text {
                    objectName: "fileName"
                    x: 12; y: fileIcon.y + fileIcon.height + 4; width: parent.width - 24; height: parent.height - y - 4
                    textFormat: Text.PlainText; text: entry.name; wrapMode: Text.WrapAnywhere
                    horizontalAlignment: Text.AlignHCenter; elide: Text.ElideRight; maximumLineCount: 2; clip: true
                    font.family: root.fontFamily; font.pixelSize: fileGrid.cellHeight < 140 ? 20 : 23
                    color: tile.focused ? root.colors.selectedText : root.colors.text
                }
                Rectangle {
                    visible: root.state.selectionMode; x: parent.width - width - 12; y: 12
                    width: 22; height: 22; radius: 5
                    color: entry.marked ? root.colors.accent : root.colors.panel
                    border.width: 2; border.color: entry.marked ? root.colors.accent : root.colors.muted
                    Text { anchors.centerIn: parent; text: entry.marked ? "✓" : ""; color: root.colors.brandInk; font.pixelSize: 17 }
                }
            }
        }
    }

    Column {
        anchors.centerIn: fileGrid; width: fileGrid.width - 24; spacing: 14
        visible: root.state.count === 0
        Text { width: parent.width; textFormat: Text.PlainText; horizontalAlignment: Text.AlignHCenter; text: root.busy ? root.tr(msg.LOADING_FOLDER) : root.state.query ? root.tr(msg.NO_MATCHING_FILES) : root.tr(msg.EMPTY_FOLDER); font.family: root.fontFamily; font.pixelSize: 28; color: root.colors.text }
        Text { width: parent.width; textFormat: Text.PlainText; horizontalAlignment: Text.AlignHCenter; text: root.tr(msg.X_OPENS_FILE_ACTIONS_SEARCH_AND_SORTING); wrapMode: Text.Wrap; font.family: root.fontFamily; font.pixelSize: 21; color: root.colors.muted }
    }

    Rectangle {
        visible: root.taskActive; x: 0; y: parent.height - 112; width: parent.width; height: 50; radius: 8
        color: root.colors.selected; border.color: root.colors.border
        Text { x: 12; y: 4; width: parent.width - 24; textFormat: Text.PlainText; text: root.state.task.summary || ""; elide: Text.ElideRight; font.family: root.fontFamily; font.pixelSize: 21; color: root.colors.text }
        FileProgress { x: 12; y: 34; width: parent.width - 24; height: 7; colors: root.colors; reducedMotion: root.reducedMotion; indeterminate: root.state.task.phase === "preparing"; from: 0; to: Math.max(1, root.state.task.totalBytes || root.state.task.totalFiles || 1); value: root.state.task.doneBytes || root.state.task.doneFiles || 0 }
    }
    Text {
        objectName: "fileCurrentDetails"
        x: 6; y: parent.height - 52; width: parent.width - 12; height: 25; textFormat: Text.PlainText
        text: [root.current.name || "", root.current.directory ? "" : root.current.sizeLabel || "",
               root.current.trash ? root.current.originalPath : root.current.modifiedLabel || "",
               root.current.symlink ? root.tr(msg.LINK) : ""].filter(function(value) { return !!value }).join("   ·   ")
        elide: Text.ElideMiddle; font.family: root.fontFamily; font.pixelSize: 21; color: root.colors.text
    }
    Text {
        objectName: "fileStatus"
        x: 6; y: parent.height - 25; width: parent.width - 12; height: 25; textFormat: Text.PlainText
        text: (root.state.selectionMode ? root.state.selectedCount + " / " + root.state.count + "   " + root.tr(msg.SELECTED)
            : root.state.count + "   " + root.tr(msg.ITEMS))
            + "   ·   " + root.state.sortLabel + (root.state.descending ? " ↓" : " ↑") + "   ·   " + root.state.filterLabel
            + (root.state.query ? "   ·   " + root.tr(msg.SEARCH) + ": " + root.state.query : "")
            + (root.state.clipboardCount ? "   ·   " + root.tr(msg.CLIPBOARD) + ": " + root.state.clipboardCount + "  " + root.state.clipboardLabel : "")
        elide: Text.ElideRight; font.family: root.fontFamily; font.pixelSize: 20; color: root.colors.muted
    }
}
