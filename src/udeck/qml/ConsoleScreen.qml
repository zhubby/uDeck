/*
[INPUT]: 依赖运行模型、SelectionViewport、显示格式和指针层。
[OUTPUT]: 提供单行表格、安全区滚动和同轨补位焦点。
[POS]: Console 专用视图；指标更新保留代理、选择与滚动位置。
[PROTOCOL]: Update this header on change, then check AGENTS.md
*/
import QtQuick
import QtQuick.Controls

Item {
    id: root
    required property var appModel
    required property var summary
    required property var colors
    required property string fontFamily
    required property int index
    required property bool contentFocused
    required property bool exitFocused
    required property string language
    required property Item hoverSurface
    property bool reducedMotion: false
    MotionTimings { id: motion; reducedMotion: root.reducedMotion }
    readonly property var msg: controller.messageKeys
    readonly property real appWidth: Math.max(180, width - 640)
    readonly property var widths: [appWidth, 112, 96, 144, 152, 104]

    function tr(key) { return controller.translate(key, language) }
    ConsoleFormat { id: format }
    function summaryText() {
        return controller.runtimeConsole.summaryText
    }
    function positionSelection() {
        viewport.ensureVisible()
    }
    SelectionViewport {
        id: viewport
        view: list; active: root.visible; reducedMotion: root.reducedMotion
    }

    Rectangle { anchors.fill: parent; radius: 7; color: root.colors.panel; border.width: 1; border.color: root.colors.rowBorder }
    Row {
        x: 16; height: 32
        Repeater {
            model: [root.tr(msg.CONSOLE_APPLICATION), root.tr(msg.CONSOLE_STATE), "CPU", root.tr(msg.CONSOLE_MEMORY), root.tr(msg.CONSOLE_UPTIME), root.tr(msg.CONSOLE_ACTIONS)]
            Text {
                required property string modelData
                required property int index
                width: root.widths[index]; height: 32; rightPadding: 12
                text: modelData; textFormat: Text.PlainText
                font.family: root.fontFamily; font.pixelSize: 20; color: root.colors.muted
                horizontalAlignment: index >= 2 && index <= 4 ? Text.AlignRight : index === 5 ? Text.AlignHCenter : Text.AlignLeft
                verticalAlignment: Text.AlignVCenter
            }
        }
    }
    Rectangle { x: 0; y: 31; width: parent.width; height: 1; color: root.colors.divider }
    ListView {
        id: list
        readonly property point pointerPosition: root.hoverSurface.containsMouse
            ? mapFromItem(root.hoverSurface, root.hoverSurface.mouseX, root.hoverSurface.mouseY) : Qt.point(-1, -1)
        objectName: "consoleList"
        x: 0; y: 32; width: parent.width; height: parent.height - 32
        model: root.appModel
        currentIndex: root.index
        highlightFollowsCurrentItem: false
        keyNavigationEnabled: false
        interactive: false
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar { palette: root.colors.controls; policy: ScrollBar.AsNeeded; interactive: false }
        FocusFrame {
            objectName: "consoleFocus"; parent: list.contentItem
            target: list.currentItem; active: root.contentFocused && root.visible
            accent: root.colors.accent; reducedMotion: root.reducedMotion; radius: 3
            visualOffsetY: list.currentItem ? list.currentItem.visualY - list.currentItem.y : 0
            followTargetMotion: !!list.currentItem && list.currentItem.reflowing
        }
        delegate: Rectangle {
            id: row
            required property int index
            required property string applicationKey
            required property string applicationName
            required property string applicationIcon
            required property string runtimeState
            required property var cpuPercent
            required property var memoryBytes
            required property var uptimeSeconds
            required property bool canQuit
            required property bool canForce
            readonly property bool selected: root.index === index && root.contentFocused
            property real visualY: 0
            property bool positioned: false
            readonly property bool reflowing: rowMove.running
            function positionRow() {
                if (!positioned) { visualY = y; return }
                rowMove.stop()
                if (root.reducedMotion || !root.visible) visualY = y
                else { rowMove.to = y; rowMove.start() }
            }
            onYChanged: positionRow()
            Component.onCompleted: Qt.callLater(function() { visualY = y; positioned = true })
            transform: Translate { y: row.visualY - row.y }
            NumberAnimation {
                id: rowMove; target: row; property: "visualY"
                duration: motion.reflow; easing.type: Easing.OutCubic
            }
            Connections {
                target: root
                function onReducedMotionChanged() { if (root.reducedMotion) row.positionRow() }
                function onVisibleChanged() { if (!root.visible) row.positionRow() }
            }
            objectName: "consoleRow-" + applicationKey
            ListView.onRemove: row.enabled = false
            width: list.width; height: 48
            color: selected ? root.colors.selected : "transparent"
            Rectangle { anchors.bottom: parent.bottom; x: 16; width: parent.width - 32; height: 1; color: root.colors.divider }
            MouseArea {
                anchors.fill: parent; cursorShape: Qt.BlankCursor
                onClicked: controller.consoleAppAction(row.applicationKey, "details")
            }
            Row {
                id: rowContent
                x: 16; height: parent.height
                Item {
                    width: root.appWidth; height: parent.height
                    ApplicationIcon {
                        x: 0; anchors.verticalCenter: parent.verticalCenter; width: 28; height: 28
                        iconName: row.applicationIcon; colors: root.colors; sourceSize: Qt.size(56, 56)
                    }
                    Text {
                        x: 40; width: parent.width - 52; height: parent.height
                        text: row.applicationName; textFormat: Text.PlainText
                        font.family: root.fontFamily; font.pixelSize: 22; color: root.colors.text
                        verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight
                    }
                }
                Text {
                    width: 112; height: parent.height; rightPadding: 8
                    text: format.state(row.runtimeState, root.language)
                    textFormat: Text.PlainText; elide: Text.ElideRight
                    font.family: root.fontFamily; font.pixelSize: 20
                    color: row.runtimeState === "paused" || row.runtimeState === "exiting" ? root.colors.accent : root.colors.muted
                    verticalAlignment: Text.AlignVCenter
                }
                Repeater {
                    model: 3
                    Text {
                        required property int index
                        width: root.widths[index + 2]; height: 48; rightPadding: 12
                        text: index === 0 ? format.percent(row.cpuPercent)
                            : index === 1 ? format.memory(row.memoryBytes, "MiB") : format.uptime(row.uptimeSeconds)
                        textFormat: Text.PlainText
                        font.family: root.fontFamily; font.pixelSize: 22
                        font.features: { "tnum": 1 }
                        color: root.colors.text; horizontalAlignment: Text.AlignRight; verticalAlignment: Text.AlignVCenter
                    }
                }
                Item {
                    width: 104; height: 48
                    Rectangle {
                        id: exitButton
                        // 显式依赖滚动和布局，静止指针随列表更新。
                        readonly property point hoverPosition: Qt.point(list.pointerPosition.x - rowContent.x - parent.x - x,
                            list.pointerPosition.y + list.contentY - row.visualY - rowContent.y - parent.y - y)
                        readonly property bool hovered: root.visible && root.contentFocused
                            && list.pointerPosition.x >= 0 && list.pointerPosition.x < list.width
                            && list.pointerPosition.y >= 0 && list.pointerPosition.y < list.height
                            && hoverPosition.x >= 0 && hoverPosition.x < width
                            && hoverPosition.y >= 0 && hoverPosition.y < height
                        objectName: "consoleExit-" + row.applicationKey
                        anchors.centerIn: parent; width: 44; height: 34; radius: 5
                        color: row.selected && root.exitFocused ? root.colors.accent : root.colors.button
                        border.width: 1; border.color: row.selected && root.exitFocused ? root.colors.accent : root.colors.buttonBorder
                        opacity: row.canQuit ? 1 : 0.45
                        Accessible.role: Accessible.Button
                        Accessible.name: root.tr(msg.CONSOLE_EXIT) + " " + row.applicationName
                        Accessible.onPressAction: if (row.canQuit) controller.consoleAppAction(row.applicationKey, "quit")
                        Image {
                            anchors.centerIn: parent; width: 24; height: 24
                            source: "image://desktop/" + encodeURIComponent("udeck-setting:box-arrow-right/"
                                + (row.selected && root.exitFocused ? root.colors.accentText : root.colors.text).toString())
                            sourceSize: Qt.size(48, 48)
                        }
                        MouseArea {
                            anchors.fill: parent; enabled: row.canQuit; cursorShape: Qt.BlankCursor
                            onClicked: controller.consoleAppAction(row.applicationKey, "quit")
                        }
                        ToolTip.visible: exitButton.hovered || (row.selected && root.exitFocused)
                        ToolTip.delay: 700
                        ToolTip.text: root.tr(msg.CONSOLE_EXIT)
                    }
                }
            }
        }
    }
    Text {
        visible: !root.summary.count
        anchors.centerIn: parent; width: parent.width - 48; horizontalAlignment: Text.AlignHCenter
        text: root.tr(msg.CONSOLE_EMPTY); textFormat: Text.PlainText
        font.family: root.fontFamily; font.pixelSize: 24; color: root.colors.muted
    }
    onIndexChanged: positionSelection()
    onVisibleChanged: positionSelection()
}
