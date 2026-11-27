// SPDX-License-Identifier: GPL-2.0-or-later
/*
[INPUT]: 依赖 Music 控制器、当前曲目、播放状态和共享主题。
[OUTPUT]: 展示封面、曲目信息、歌词和固定播放栏。
[POS]: Music 播放页；歌词可用时与封面并列。
[PROTOCOL]: Update this header on change, then check AGENTS.md
*/
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Shapes
import "../../common/qml"

Item {
    id: surface
    required property var colors
    required property var host
    readonly property var msg: host.msg
    readonly property var track: host.state.current
    readonly property var media: host.state.media
    readonly property var lyrics: controller.lyrics
    readonly property bool hasLyrics: lyrics.lines.length > 0
    readonly property bool compact: height < 500
    readonly property int gutter: width < 1050 ? 28 : 52
    readonly property int activeControl: host.state.control
    readonly property real duration: media.duration || 0
    readonly property real position: media.position || 0

    component TransportButton: SuiteButton {
        id: button
        required property string symbolPath
        required property string command
        property bool primary: false
        colors: surface.colors
        fontFamily: surface.host.fontFamily
        compact: surface.compact
        radius: height / 2
        implicitWidth: primary ? implicitHeight : implicitHeight + 4
        implicitHeight: primary ? (compact ? 46 : 54) : (compact ? 38 : 44)
        color: primary ? (selected ? colors.accent : colors.buttonSelected)
                       : (selected ? colors.buttonSelected : colors.button)
        iconComponent: Shape {
            width: 24
            height: 24
            ShapePath {
                fillColor: button.primary && button.selected ? button.colors.accentText : button.colors.text
                strokeColor: "transparent"
                PathSvg { path: button.symbolPath }
            }
        }
        onActivated: controller.command(command)
    }

    Rectangle {
        anchors.fill: parent
        color: surface.colors.background
    }

    Item {
        id: hero
        anchors.top: parent.top
        anchors.bottom: dock.top
        anchors.topMargin: surface.compact ? 14 : 24
        anchors.bottomMargin: anchors.topMargin
        anchors.horizontalCenter: parent.horizontalCenter
        width: Math.min(surface.width - 2 * surface.gutter, surface.hasLyrics ? 1120 : 960)
        readonly property real coverColumn: surface.hasLyrics
            ? Math.min(width * 0.36, Math.max(width * 0.28, height - 88), 360)
            : width / 2
        readonly property real gap: surface.width < 1050 ? 28 : 52
        readonly property real coverSize: Math.max(1, Math.min(
            surface.hasLyrics ? coverColumn : coverColumn - gap / 2,
            height - (surface.hasLyrics ? metadata.implicitHeight + 14 : 0),
            surface.hasLyrics ? 320 : 390))

        Artwork {
            id: cover
            objectName: "musicPlayerArtwork"
            colors: surface.colors
            fontFamily: surface.host.fontFamily
            identity: surface.track.id || ""
            kind: "music"
            cover: surface.track.cover || ""
            radius: 10
            width: hero.coverSize
            height: width
            x: surface.hasLyrics ? 0 : hero.coverColumn - hero.gap / 2 - width
            y: surface.hasLyrics ? (hero.height - height - 14 - metadata.implicitHeight) / 2
                                 : (hero.height - height) / 2
        }

        Column {
            id: metadata
            x: surface.hasLyrics ? cover.x : hero.coverColumn + hero.gap / 2
            y: surface.hasLyrics ? cover.y + cover.height + 14 : (hero.height - implicitHeight) / 2
            width: surface.hasLyrics ? hero.coverColumn : hero.width - x
            spacing: surface.compact ? 3 : 5

            Text {
                width: parent.width
                text: surface.track.title || ""
                textFormat: Text.PlainText
                color: surface.colors.text
                font.family: surface.host.fontFamily
                font.weight: Font.DemiBold
                font.pixelSize: surface.hasLyrics ? (surface.compact ? 25 : 34) : (surface.compact ? 37 : 56)
                wrapMode: Text.Wrap
                maximumLineCount: 2
                elide: Text.ElideRight
            }
            Text {
                width: parent.width
                visible: text.length > 0
                text: surface.track.artist || ""
                textFormat: Text.PlainText
                color: surface.colors.muted
                font.family: surface.host.fontFamily
                font.pixelSize: surface.hasLyrics ? 18 : (surface.compact ? 23 : 26)
                elide: Text.ElideRight
            }
            Text {
                width: parent.width
                visible: text.length > 0 && text !== surface.track.title && text !== surface.track.artist
                text: surface.track.album || ""
                textFormat: Text.PlainText
                color: surface.colors.muted
                font.family: surface.host.fontFamily
                font.pixelSize: surface.hasLyrics ? 16 : (surface.compact ? 18 : 20)
                elide: Text.ElideRight
            }
        }

        MusicLyrics {
            x: hero.coverColumn + hero.gap
            width: hero.width - x
            height: hero.height
            visible: surface.hasLyrics
            fontFamily: surface.host.fontFamily
            colors: surface.colors
            heading: surface.host.tr(surface.msg.LYRICS)
            lines: surface.lyrics.lines
            timed: surface.lyrics.timed
            position: surface.position
            compact: surface.compact
            seekable: surface.duration > 0 && !surface.media.loading
            onSeekRequested: seconds => controller.seek(seconds)
        }
    }

    Rectangle {
        id: dock
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: surface.compact ? 100 : 118
        color: surface.colors.header
        Rectangle { width: parent.width; height: 1; color: surface.colors.divider }

        ColumnLayout {
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.verticalCenter: parent.verticalCenter
            width: Math.min(parent.width - 2 * surface.gutter, 1120)
            spacing: surface.compact ? 4 : 7

            RowLayout {
                Layout.fillWidth: true
                spacing: 16
                Text {
                    text: surface.host.time(surface.position)
                    color: surface.colors.text
                    font.family: surface.host.fontFamily
                    font.pixelSize: 16
                }
                Slider {
                    id: progress
                    objectName: "musicProgress"
                    Layout.fillWidth: true
                    Layout.preferredHeight: 28
                    Accessible.name: surface.host.tr(surface.msg.POSITION_IN_SECONDS)
                    focusPolicy: Qt.NoFocus
                    palette: surface.colors.controls
                    enabled: surface.duration > 0 && !surface.media.loading
                    to: surface.duration || 1
                    value: surface.position
                    onMoved: controller.seek(value)
                    background: Rectangle {
                        x: progress.leftPadding + progress.handle.width / 2
                        y: (progress.height - height) / 2
                        width: progress.availableWidth - progress.handle.width
                        height: 4
                        radius: 2
                        color: surface.colors.track
                        Rectangle {
                            width: parent.width * progress.visualPosition
                            height: parent.height
                            radius: 2
                            color: surface.colors.accent
                        }
                    }
                    handle: Rectangle {
                        width: progress.pressed ? 15 : 12
                        height: width
                        radius: width / 2
                        x: progress.leftPadding + progress.visualPosition * (progress.availableWidth - width)
                        y: (progress.height - height) / 2
                        color: surface.colors.accent
                    }
                }
                Text {
                    text: surface.host.time(surface.duration)
                    color: surface.colors.muted
                    font.family: surface.host.fontFamily
                    font.pixelSize: 16
                }
            }

            Item {
                Layout.fillWidth: true
                Layout.preferredHeight: transport.implicitHeight
                readonly property real statusWidth: (width - transport.width) / 2 - 22

                Column {
                    anchors.left: parent.left
                    anchors.verticalCenter: parent.verticalCenter
                    width: parent.statusWidth
                    spacing: 2
                    Text {
                        width: parent.width
                        text: surface.media.loading ? surface.host.tr(surface.msg.LOADING) : surface.media.output || ""
                        textFormat: Text.PlainText
                        color: surface.colors.text
                        font.family: surface.host.fontFamily
                        font.pixelSize: 17
                        elide: Text.ElideRight
                    }
                    Text {
                        text: surface.track.format || ""
                        color: surface.colors.muted
                        font.family: surface.host.fontFamily
                        font.pixelSize: 15
                    }
                }

                Row {
                    id: transport
                    anchors.centerIn: parent
                    spacing: surface.compact ? 14 : 18
                    TransportButton {
                        objectName: "musicPrevious"
                        anchors.verticalCenter: parent.verticalCenter
                        text: surface.host.tr(surface.msg.PREVIOUS_TRACK)
                        symbolPath: "M 4,5 H 7 V 19 H 4 Z M 20,5 L 8,12 L 20,19 Z"
                        selected: surface.activeControl === 0
                        command: "previous"
                    }
                    TransportButton {
                        objectName: "musicPlayPause"
                        anchors.verticalCenter: parent.verticalCenter
                        primary: true
                        text: surface.host.tr(surface.media.playing ? surface.msg.PAUSE : surface.msg.PLAY)
                        symbolPath: surface.media.playing ? "M 6,5 H 10 V 19 H 6 Z M 14,5 H 18 V 19 H 14 Z"
                                                          : "M 8,4 L 21,12 L 8,20 Z"
                        selected: surface.activeControl === 1
                        command: "play-pause"
                    }
                    TransportButton {
                        objectName: "musicNext"
                        anchors.verticalCenter: parent.verticalCenter
                        text: surface.host.tr(surface.msg.NEXT_TRACK)
                        symbolPath: "M 4,5 L 16,12 L 4,19 Z M 17,5 H 20 V 19 H 17 Z"
                        selected: surface.activeControl === 2
                        command: "next"
                    }
                }

                Column {
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    width: parent.statusWidth
                    spacing: 2
                    Text {
                        width: parent.width
                        horizontalAlignment: Text.AlignRight
                        text: surface.host.tr(surface.msg.SHUFFLE) + " · "
                              + surface.host.tr(surface.host.state.shuffle ? surface.msg.ON : surface.msg.OFF)
                        color: surface.host.state.shuffle ? surface.colors.accent : surface.colors.muted
                        font.family: surface.host.fontFamily
                        font.pixelSize: 16
                        elide: Text.ElideRight
                    }
                    Text {
                        width: parent.width
                        horizontalAlignment: Text.AlignRight
                        text: surface.host.tr(surface.msg.REPEAT) + " · " + surface.host.state.repeatLabel
                        color: surface.host.state.repeat !== "off" ? surface.colors.accent : surface.colors.muted
                        font.family: surface.host.fontFamily
                        font.pixelSize: 16
                        elide: Text.ElideRight
                    }
                }
            }
        }
    }
}
