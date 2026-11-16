/*
[INPUT]: 依赖主页条目、启动身份、主题和减少动画开关。
[OUTPUT]: 提供主页卡片、单一焦点与即时启动反馈。
[POS]: 桌面主页视图；控制器负责选择和启动。
[PROTOCOL]: Update this header on change, then check AGENTS.md
*/
pragma ComponentBehavior: Bound

import QtQuick

Item {
    id: screen
    required property var items
    required property var colors
    required property string fontFamily
    required property string language
    property int index: 0
    property bool contentFocused: true
    property bool reducedMotion: false
    property var launchState: ({})
    MotionTimings { id: motion; reducedMotion: screen.reducedMotion }
    readonly property int tileWidth: 180
    readonly property var selectedItem: items[index] || ({})

    function positionSelection() {
        shortcuts.positionViewAtIndex(index, ListView.Contain)
        // Keep room for the selected card's scale at either edge.
        const start = index * (tileWidth + shortcuts.spacing)
        const minimum = start + tileWidth - shortcuts.width + shortcuts.rightMargin
        const maximum = start - shortcuts.leftMargin
        shortcuts.contentX = Math.max(minimum, Math.min(shortcuts.contentX, maximum))
    }

    onWidthChanged: Qt.callLater(positionSelection)

    ListView {
        id: shortcuts
        objectName: "homeStrip"
        width: Math.min(parent.width, 6 * screen.tileWidth + 5 * spacing + 20)
        anchors.horizontalCenter: parent.horizontalCenter
        height: Math.min(236, Math.max(160, parent.height - 108))
        orientation: ListView.Horizontal
        spacing: 18
        leftMargin: 10
        rightMargin: leftMargin
        model: screen.items
        currentIndex: screen.index
        keyNavigationEnabled: false
        interactive: false
        boundsBehavior: Flickable.StopAtBounds
        clip: true
        cacheBuffer: 1200
        FocusFrame {
            objectName: "homeFocus"; parent: shortcuts.contentItem
            target: shortcuts.currentItem; active: screen.contentFocused && screen.visible
            accent: screen.colors.accent; reducedMotion: screen.reducedMotion
            topInset: 12; bottomInset: 12; radius: 16
        }

        delegate: Item {
            id: tile
            required property var modelData
            required property int index
            objectName: "homeTile-" + index
            property bool selected: screen.index === index && screen.contentFocused
            readonly property bool launchPending: !!screen.launchState.pending && modelData.id === screen.launchState.applicationId
            width: screen.tileWidth
            height: shortcuts.height
            Accessible.role: Accessible.Button
            Accessible.name: modelData.name
            Accessible.description: modelData.reason || modelData.subtitle
            Accessible.focused: selected

            Rectangle {
                id: card
                anchors.centerIn: parent
                width: parent.width
                height: parent.height - 24
                radius: 16
                color: tile.selected ? screen.colors.selected : screen.colors.panel
                border.width: 1; border.color: screen.colors.border
                scale: tile.launchPending ? 0.98 : 1
                opacity: tile.modelData.disabled ? 0.5 : 1
                Behavior on scale {
                    NumberAnimation { duration: motion.press; easing.type: Easing.OutCubic }
                }

                Column {
                    anchors.centerIn: parent
                    spacing: 16
                    Rectangle {
                        width: Math.min(96, card.height - 64)
                        height: width
                        radius: 22
                        anchors.horizontalCenter: parent.horizontalCenter
                        color: screen.colors.artwork(tile.modelData.homeKind)
                        HomeIcon {
                            objectName: "homeIcon-" + tile.modelData.homeKind
                            anchors.centerIn: parent
                            width: parent.width * 0.76
                            height: width
                            kind: tile.modelData.homeKind
                        }
                    }
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        textFormat: Text.PlainText
                        text: tile.modelData.name
                        color: tile.selected ? screen.colors.accent : screen.colors.text
                        font.family: screen.fontFamily
                        font.pixelSize: 26
                        font.weight: tile.selected ? Font.DemiBold : Font.Normal
                    }
                }
            }
        }
    }

    Rectangle {
        x: 10
        y: shortcuts.height + 24
        width: 3
        height: 64
        radius: 1
        color: screen.colors.accent
    }
    Text {
        objectName: "homeSelectedTitle"
        x: 32
        y: shortcuts.height + 14
        width: parent.width - 144
        textFormat: Text.PlainText
        text: screen.selectedItem.name || ""
        font.family: screen.fontFamily
        font.pixelSize: 32
        font.weight: Font.DemiBold
        color: screen.colors.text
    }
    Text {
        objectName: "homeSelectedDescription"
        x: 32
        y: shortcuts.height + 60
        width: parent.width - 48
        textFormat: Text.PlainText
        text: screen.launchState.pending && screen.selectedItem.id === screen.launchState.applicationId
            ? controller.translate(controller.messageKeys.OPENING_APPLICATION, screen.language)
            : screen.selectedItem.reason || screen.selectedItem.subtitle || ""
        font.family: screen.fontFamily
        font.pixelSize: 22
        color: screen.colors.muted
        wrapMode: Text.Wrap
        maximumLineCount: 2
        elide: Text.ElideRight
    }
    Text {
        anchors.right: parent.right
        anchors.rightMargin: 12
        y: shortcuts.height + 22
        text: (screen.index + 1) + " / " + screen.items.length
        font.family: screen.fontFamily
        font.pixelSize: 20
        color: screen.colors.muted
    }
}
