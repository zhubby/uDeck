// SPDX-License-Identifier: GPL-2.0-or-later
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../../../qml" as Shared
import "../../common/qml"

Item {
    id: surface
    readonly property var msg: host ? host.msg : ({})
    required property var colors
    required property var host
    property var appState: host ? host.state : ({current:{},media:{}})
    readonly property bool compact: height < 480
    readonly property int contentMargin: compact ? 20 : host && host.width < 1100 ? 40 : 64
    readonly property int focusedControl: appState.control || 0
    onFocusedControlChanged: Qt.callLater(function() {
        playerScroll.contentY = Math.max(0, playerScroll.contentHeight - playerScroll.height)
    })
    function tr(s){return host?host.tr(s):s}
    Rectangle { anchors.fill: parent; color: surface.colors.background }
    RowLayout {
        anchors.fill: parent; anchors.leftMargin: surface.contentMargin; anchors.rightMargin: surface.contentMargin; spacing: surface.compact ? 24 : 48
        Artwork { fontFamily: surface.host.fontFamily; colors: surface.colors; Layout.preferredWidth: Math.max(1, Math.min(surface.height - surface.contentMargin * 2, surface.compact ? 240 : host && host.width<1100?280:350)); Layout.preferredHeight: width; cover: appState.current.cover||""; kind: "music" }
        Flickable {
            id: playerScroll
            Layout.fillWidth: true; Layout.fillHeight: true
            Layout.topMargin: surface.compact ? 4 : 20; Layout.bottomMargin: surface.compact ? 4 : 20
            contentWidth: width; contentHeight: Math.max(height, details.implicitHeight)
            clip: true; boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { palette: surface.colors.controls; }
            ColumnLayout {
                id: details
                width: playerScroll.width; height: implicitHeight
                y: Math.max(0, (playerScroll.height - implicitHeight) / 2)
                spacing: surface.compact ? 4 : 20
                Text { font.family: surface.host.fontFamily; text: surface.tr(msg.NOW_PLAYING); color: surface.colors.muted; font.pixelSize: surface.compact ? 18 : 20 }
                Text { font.family: surface.host.fontFamily; Layout.fillWidth: true; text: appState.current.title||""; color: surface.colors.text; font.pixelSize: surface.compact ? 26 : 36; wrapMode: Text.Wrap; maximumLineCount: surface.compact ? 2 : 3; elide: Text.ElideRight }
                Text { font.family: surface.host.fontFamily; Layout.fillWidth: true; visible: !surface.compact || text.length > 0; text: appState.current.artist||appState.current.album||""; color: surface.colors.muted; font.pixelSize: surface.compact ? 18 : 24; wrapMode: Text.Wrap }
                Text { font.family: surface.host.fontFamily; Layout.fillWidth: true; text: (appState.current.format||"")+"  ·  "+(appState.media.output||""); color: surface.colors.muted; font.pixelSize: surface.compact ? 16 : 18; elide: Text.ElideRight }
                Item { visible: !surface.compact; Layout.preferredHeight: 12 }
                Slider { palette: surface.colors.controls; Layout.fillWidth: true; from: 0; to: appState.media.duration||1; value: appState.media.position||0; onMoved: controller.seek(value) }
                Text { font.family: surface.host.fontFamily; text: host?host.time(appState.media.position)+" / "+host.time(appState.media.duration):""; color: surface.colors.muted; font.pixelSize: surface.compact ? 18 : 20 }
                RowLayout {
                    spacing: 14
                    SuiteButton { fontFamily: surface.host.fontFamily; colors: surface.colors; text: "⏮"; selected: appState.control===0; onActivated: controller.command("previous") }
                    SuiteButton { fontFamily: surface.host.fontFamily; colors: surface.colors; text: appState.media.playing?surface.tr(msg.PAUSE):surface.tr(msg.PLAY); selected: appState.control===1; onActivated: controller.command("play-pause") }
                    SuiteButton { fontFamily: surface.host.fontFamily; colors: surface.colors; text: "⏭"; selected: appState.control===2; onActivated: controller.command("next") }
                }
                Text { font.family: surface.host.fontFamily; Layout.fillWidth: true; text: surface.tr(msg.SHUFFLE)+": "+(appState.shuffle?surface.tr(msg.ON):surface.tr(msg.OFF))+"   ·   "+surface.tr(msg.REPEAT)+": "+(appState.repeatLabel||surface.tr(msg.OFF)); color: surface.colors.muted; font.pixelSize: surface.compact ? 16 : 18; wrapMode: Text.Wrap }
            }
        }
    }
    Text { font.family: surface.host.fontFamily; anchors.centerIn: parent; visible: appState.media.loading||false; text: surface.tr(msg.LOADING); color: surface.colors.text; font.pixelSize: 28 }
}
