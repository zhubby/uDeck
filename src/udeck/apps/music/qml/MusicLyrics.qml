// SPDX-License-Identifier: GPL-2.0-or-later
/*
[INPUT]: 依赖已解析歌词、播放位置和共享主题。
[OUTPUT]: 展示可滚动的歌词，突出当前句并发出定位请求。
[POS]: Music 播放页的歌词区；播放栏独立于歌词滚动。
[PROTOCOL]: Update this header on change, then check AGENTS.md
*/
import QtQuick
import QtQuick.Controls

Item {
    id: lyrics
    objectName: "musicLyrics"
    required property var colors
    required property string fontFamily
    required property string heading
    required property var lines
    required property bool timed
    required property bool seekable
    required property real position
    property bool compact: false
    signal seekRequested(real seconds)

    readonly property int activeIndex: {
        if (!timed)
            return -1
        const milliseconds = Math.round(position * 1000)
        let first = 0
        let end = lines.length
        while (first < end) {
            const middle = Math.floor((first + end) / 2)
            if (lines[middle].start <= milliseconds)
                first = middle + 1
            else
                end = middle
        }
        return first - 1
    }

    function followCurrentLine() {
        if (view.moving)
            return
        if (activeIndex >= 0)
            view.positionViewAtIndex(activeIndex, ListView.Center)
        else
            view.positionViewAtBeginning()
    }

    onActiveIndexChanged: Qt.callLater(followCurrentLine)
    onLinesChanged: Qt.callLater(followCurrentLine)
    onHeightChanged: Qt.callLater(followCurrentLine)
    Component.onCompleted: Qt.callLater(followCurrentLine)

    Text {
        id: label
        anchors.top: parent.top
        anchors.left: parent.left
        text: lyrics.heading
        color: lyrics.colors.muted
        font.family: lyrics.fontFamily
        font.pixelSize: 17
        font.weight: Font.DemiBold
    }

    Rectangle {
        anchors.top: label.bottom
        anchors.topMargin: 9
        width: parent.width
        height: 1
        color: lyrics.colors.divider
    }

    ListView {
        id: view
        objectName: "musicLyricsView"
        anchors.top: label.bottom
        anchors.topMargin: 16
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        clip: true
        model: lyrics.lines
        spacing: 3
        bottomMargin: lyrics.timed ? height / 2 : 0
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar { palette: lyrics.colors.controls }
        delegate: Rectangle {
            id: line
            required property int index
            required property var modelData
            readonly property bool active: index === lyrics.activeIndex && !!modelData.text
            readonly property bool clickable: lyrics.timed && lyrics.seekable && !!modelData.text
            objectName: active ? "activeLyricLine" : "lyricLine"
            width: view.width - 14
            height: lineText.implicitHeight + (lyrics.compact ? 12 : 16)
            radius: 6
            color: active ? lyrics.colors.selected : pointer.hovered && clickable ? lyrics.colors.panel : "transparent"
            Accessible.role: clickable ? Accessible.Button : Accessible.StaticText
            Accessible.name: modelData.text
            Accessible.onPressAction: if (clickable) lyrics.seekRequested(modelData.start / 1000)

            Rectangle {
                visible: line.active
                width: 3
                height: Math.min(24, parent.height - 10)
                radius: 1.5
                anchors.left: parent.left
                anchors.verticalCenter: parent.verticalCenter
                color: lyrics.colors.accent
            }

            Text {
                id: lineText
                objectName: "lyricText"
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.margins: 14
                anchors.verticalCenter: parent.verticalCenter
                text: line.modelData.text
                textFormat: Text.PlainText
                wrapMode: Text.Wrap
                color: line.active ? lyrics.colors.accent : lyrics.timed ? lyrics.colors.muted : lyrics.colors.text
                font.family: lyrics.fontFamily
                font.pixelSize: lyrics.compact ? 22 : 27
                font.weight: line.active ? Font.DemiBold : Font.Normal
            }

            HoverHandler { id: pointer; enabled: line.clickable; cursorShape: Qt.PointingHandCursor }
            TapHandler {
                enabled: line.clickable
                onTapped: lyrics.seekRequested(line.modelData.start / 1000)
            }
        }
    }

    Rectangle {
        anchors.top: view.top
        width: view.width - 14
        height: 18
        visible: !view.atYBeginning
        gradient: Gradient {
            GradientStop { position: 0; color: lyrics.colors.background }
            GradientStop { position: 1; color: "transparent" }
        }
    }
    Rectangle {
        anchors.bottom: view.bottom
        width: view.width - 14
        height: 18
        visible: !view.atYEnd
        gradient: Gradient {
            GradientStop { position: 0; color: "transparent" }
            GradientStop { position: 1; color: lyrics.colors.background }
        }
    }
}
