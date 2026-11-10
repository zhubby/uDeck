pragma ComponentBehavior: Bound

import QtQuick

Item {
    id: screen
    required property var items
    required property var colors
    required property string fontFamily
    property int index: 0
    property bool contentFocused: true
    property bool reducedMotion: false
    readonly property var selectedItem: items[index] || ({})

    function positionSelection() {
        shortcuts.positionViewAtIndex(index, ListView.Contain)
    }

    onWidthChanged: Qt.callLater(positionSelection)

    ListView {
        id: shortcuts
        objectName: "homeStrip"
        width: parent.width
        height: Math.min(236, Math.max(160, parent.height - 108))
        orientation: ListView.Horizontal
        spacing: 18
        leftMargin: Math.max(10, (width - 6 * 180 - 5 * spacing) / 2)
        rightMargin: leftMargin
        model: screen.items
        currentIndex: screen.index
        keyNavigationEnabled: false
        interactive: false
        boundsBehavior: Flickable.StopAtBounds
        clip: true
        cacheBuffer: 1200

        delegate: Item {
            id: tile
            required property var modelData
            required property int index
            objectName: "homeTile-" + index
            property bool selected: screen.index === index && screen.contentFocused
            width: 180
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
                border.width: tile.selected ? 3 : 1
                border.color: tile.selected ? screen.colors.accent : screen.colors.border
                scale: tile.selected ? 1.035 : 1
                opacity: tile.modelData.disabled ? 0.5 : 1
                Behavior on scale {
                    NumberAnimation { duration: screen.reducedMotion ? 0 : 140; easing.type: Easing.OutCubic }
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
        text: screen.selectedItem.reason || screen.selectedItem.subtitle || ""
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
